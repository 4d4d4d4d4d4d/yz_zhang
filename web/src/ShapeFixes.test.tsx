// CLI-083 响应形状扫除第一次跑就扫出来的、**界面上**的后果（100 号 spec）。
//
// 扫描闸门证明 SDK 的类型与服务端对上了。这里验的是类型对上之后，
// 界面有没有真的用上那些此前看不见的字段：
// - 证据包文件要带上「证明力边界」说明；
// - 实名核验 HTTP 200 而转人工时，不能告诉用户「成功」。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { DisputePanel } from './DisputePanel';
import { AppProvider } from './store';

function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
  errors: Record<string, { status: number; code: string; message: string }> = {},
): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const err = errors[path];
    if (err) {
      return {
        ok: false, status: err.status,
        text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }),
      };
    }
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('CLI-083 证据包文件要带上证明力边界说明', () => {
  const NOTICE = '本文所载「平台处理决定」系依当事人事先约定作出的合同履行调整，不是法律意义上的仲裁裁决，不具有强制执行力。';
  const DISPUTE = {
    id: 9, task_id: 7, contract_id: 3, opened_by: 1, reason: '交付不符合约定要求', status: 'resolved',
    evidence: {}, settlement_proposal: null, verdict_executor_share_bps: 3000,
    verdict_reason: '部分完成', split_base_cents: 20000, escalated: false,
    resolved_at: '2026-10-01T00:00:00Z', response_deadline: '2026-09-30T00:00:00Z',
    appealable: false, respondent_id: 2, respondent_spoke: true,
  };

  it('下载的文件里有 evidentiary_notice 与 integrity，而不只是 package + sha256', async () => {
    // 抓下写进 Blob 的文本：jsdom 里没有真的下载
    let written = '';
    const OrigBlob = globalThis.Blob;
    vi.stubGlobal('Blob', class extends OrigBlob {
      constructor(parts: BlobPart[], opts?: BlobPropertyBag) {
        super(parts, opts);
        written = parts.map(String).join('');
      }
    });
    vi.stubGlobal('URL', Object.assign(Object.create(URL), {
      createObjectURL: () => 'blob:x', revokeObjectURL: () => {},
    }));

    const client = makeClient({
      '/tasks/7/dispute': DISPUTE,
      '/disputes/9/statements': [],
      '/legal/disputes/9/evidence-export': {
        package: { dispute_id: 9, timeline: [] },
        sha256: 'abc123',
        integrity: { chain_valid: true, chain_entries: 12, third_party_backed_to_seq: 12,
                     uncovered_entries: 0, receipts: [] },
        evidentiary_notice: { signatures: '平台见证签名', chain: '已由第三方背书', decision: NOTICE },
      },
    });
    render(<DisputePanel client={client} taskId={7} meId={1} />);
    fireEvent.click(await screen.findByText('导出证据包'));

    await waitFor(() => expect(written).not.toBe(''));
    const saved = JSON.parse(written);
    // 改造前文件是 `{...package, sha256}`——下面三条一条都不会在
    expect(saved.evidentiary_notice.decision).toContain('不是法律意义上的仲裁裁决');
    expect(saved.integrity.chain_valid).toBe(true);
    expect(saved.sha256).toBe('abc123');
  });
});

describe('ACC-020 实名核验：HTTP 200 不等于通过', () => {
  const ME = {
    id: 2, phone: '138****0002', nickname: '新人', bio: '', city: '', lat: null, lng: null,
    skills: [], interests: [], is_verified: false, is_admin: false, credit_score: 100,
    rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
  };

  function openProfile(verifyResult: unknown, calls: Array<{ method: string; path: string; body: unknown }> = [],
    errors: Record<string, { status: number; code: string; message: string }> = {}) {
    localStorage.setItem('token', 'tok');
    // 资料页还会读协议状态等别的接口；测试桩的默认返回是 []，
    // 对那些返回对象的接口不成立，所以给出真实形状
    const client = makeClient({
      '/users/me': ME, '/users/me/verify': verifyResult,
      '/legal/agreements': { current_version: '2026-09', documents: [], sensitive_scopes: [], rights: {} },
    }, calls, errors);
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    return calls;
  }

  it('转人工时说「正在人工审核」，**不说成功**', async () => {
    openProfile({ is_verified: false, status: 'manual_review' });
    fireEvent.change(await screen.findByLabelText('真实姓名'), { target: { value: '张三' } });
    fireEvent.change(screen.getByLabelText('身份证号'), { target: { value: '110101199001011235' } });
    fireEvent.click(screen.getByText('提交实名认证'));

    await waitFor(() => expect(screen.getByText(/正在人工审核/)).toBeTruthy());
    expect(screen.queryByText(/实名认证已通过/)).toBeNull();
    expect(screen.queryByText(/实名认证成功/)).toBeNull();
  });

  it('提交的是用户填的，表单**不预填任何证件号**', async () => {
    const calls = openProfile({ is_verified: true, status: 'verified' });
    const idInput = await screen.findByLabelText('身份证号') as HTMLInputElement;
    // 原来的 prompt 预填了 110101199001011234——照着默认值点确定就会把它提交上去
    expect(idInput.value).toBe('');
    fireEvent.change(screen.getByLabelText('真实姓名'), { target: { value: '李四' } });
    fireEvent.change(idInput, { target: { value: '11010119900101123X' } });
    fireEvent.click(screen.getByText('提交实名认证'));

    await waitFor(() => expect(screen.getByText('实名认证已通过')).toBeTruthy());
    const sent = calls.find((c) => c.method === 'POST' && c.path === '/users/me/verify');
    expect(sent?.body).toEqual({ real_name: '李四', id_number: '11010119900101123X' });
  });

  it('证件号已被绑定时把服务端的话显示出来', async () => {
    openProfile({}, [], { '/users/me/verify': { status: 409, code: 'id_already_bound', message: '该证件号已绑定其它账号' } });
    fireEvent.change(await screen.findByLabelText('真实姓名'), { target: { value: '王五' } });
    fireEvent.change(screen.getByLabelText('身份证号'), { target: { value: '110101199001011235' } });
    fireEvent.click(screen.getByText('提交实名认证'));
    await waitFor(() => expect(screen.getByText(/该证件号已绑定其它账号/)).toBeTruthy());
  });

  it('格式不对时不发请求', async () => {
    const calls = openProfile({ is_verified: true, status: 'verified' });
    fireEvent.change(await screen.findByLabelText('真实姓名'), { target: { value: '赵六' } });
    fireEvent.change(screen.getByLabelText('身份证号'), { target: { value: '123' } });
    fireEvent.click(screen.getByText('提交实名认证'));
    await waitFor(() => expect(screen.getByText(/15 或 18 位身份证号/)).toBeTruthy());
    expect(calls.some((c) => c.path === '/users/me/verify')).toBe(false);
  });
});
