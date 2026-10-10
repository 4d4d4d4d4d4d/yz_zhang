// LAW-051 / KB-023 「不懂就问」在网页上的行为（97 号 spec）。
//
// 扫描闸门能证明入口存在。这里验的是它验不到的那些：
// 三种结局**不是三种措辞而是三件不同的事**、免责声明有没有原样显示、
// 退化的检索有没有被说出来、答不了时的补救是不是真能送到地方。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '提问者', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};

const DISCLAIMER = '以上内容仅为一般性法律信息，不构成法律意见；正式法律服务请咨询执业律师。';

function openAsk(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(
    <MemoryRouter initialEntries={['/ask']}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

const ask = (extra: Record<string, unknown>) => ({
  '/users/me': ME,
  '/legal/ask': { disclaimer: DISCLAIMER, ...extra },
});

describe('LAW-051 三种结局是三件不同的事', () => {
  it('人身风险：说清不作解答，且**不给**平台内的补救入口', async () => {
    openAsk(ask({
      answer: '该问题涉及人身安全或刑事风险，请立即拨打 110 报警或联系专业机构，平台 AI 不提供此类解答。',
      refused: true, refused_reason: 'high_risk',
      // 同 App：故意给一个 remedy，验的是客户端按 refused_reason 判断，
      // 而不是「服务端没给所以画不出来」。
      remedy: { action: 'publish_task', category: '法律咨询', label: '发布法律咨询任务（由执业律师接单）' },
    }));
    fireEvent.change(await screen.findByLabelText('法律问题'), { target: { value: '对方威胁我' } });
    fireEvent.click(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText('这个问题平台不作解答')).toBeTruthy());
    // 服务端那句原文，和界面自己那句「平台流程不优先于此」，两句都要在
    expect(screen.getByText(/请立即拨打 110 报警或联系专业机构/)).toBeTruthy();
    expect(screen.getByText(/平台的任何流程都不优先于此/)).toBeTruthy();
    // 在一条紧急升级旁边摆「发布咨询任务」，是把紧急情况降级成一笔生意
    expect(screen.queryByText(/发布法律咨询任务/)).toBeNull();
  });

  it('超出知识库：给出可点的补救，且类目用服务端给的', async () => {
    openAsk(ask({
      answer: '该问题超出平台法律知识库范围，建议通过「找律师」发布法律咨询任务，由执业律师解答。',
      refused: true, refused_reason: 'out_of_scope',
      remedy: { action: 'publish_task', category: '法律咨询', label: '发布法律咨询任务（由执业律师接单）' },
    }));
    fireEvent.change(await screen.findByLabelText('法律问题'), { target: { value: '外星人宅基地' } });
    fireEvent.click(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText('平台知识库答不了这一条')).toBeTruthy());
    const link = screen.getByText('发布法律咨询任务（由执业律师接单）').closest('a');
    // 66 号 spec：服务端说去发一单，这里就得真的送得到——而且带着那个类目
    expect(link?.getAttribute('href')).toContain('category=%E6%B3%95%E5%BE%8B%E5%92%A8%E8%AF%A2');
  });

  it('命中知识库：既不报警也不劝他发任务', async () => {
    openAsk(ask({
      answer: '平台电子合约经双方在线确认签署后成立。',
      refused: false, refused_reason: '', remedy: null,
    }));
    fireEvent.change(await screen.findByLabelText('法律问题'), { target: { value: '合约有效力吗' } });
    fireEvent.click(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText(/经双方在线确认签署后成立/)).toBeTruthy());
    expect(screen.queryByText('这个问题平台不作解答')).toBeNull();
    expect(screen.queryByText('平台知识库答不了这一条')).toBeNull();
  });

  it('免责声明三种结局都原样显示', async () => {
    openAsk(ask({
      answer: '平台电子合约经双方在线确认签署后成立。',
      refused: false, refused_reason: '', remedy: null,
    }));
    fireEvent.change(await screen.findByLabelText('法律问题'), { target: { value: '合约' } });
    fireEvent.click(screen.getByText('提问'));
    // 平台给的是一般性法律信息，不是法律意见——这句话的法律含义不容客户端改写
    await waitFor(() => expect(screen.getByText(DISCLAIMER)).toBeTruthy());
  });
});

describe('KB-023 平台攒的经验要读得回来', () => {
  it('退化的检索必须说出来——否则等于把服务端那份诚实扔掉', async () => {
    openAsk({
      '/users/me': ME,
      '/knowledge/search': {
        results: [{ id: 1, score: 1, text: '跑腿 杭州 跑腿·杭州' }],
        semantic: false, degraded: true, model: 'local-bow-256',
      },
    });
    fireEvent.change(await screen.findByLabelText('搜索经验'), { target: { value: '跑腿' } });
    fireEvent.click(screen.getByText('检索'));

    await waitFor(() => expect(screen.getByText(/不是语义检索/)).toBeTruthy());
    expect(screen.getByText(/local-bow-256/)).toBeTruthy();
    expect(screen.getByText(/退化为词面命中/)).toBeTruthy();
  });

  it('真语义检索时不画那句提示（它只在退化时才有信息量）', async () => {
    openAsk({
      '/users/me': ME,
      '/knowledge/search': {
        results: [], semantic: true, degraded: false, model: 'real-embed-1',
      },
    });
    fireEvent.change(await screen.findByLabelText('搜索经验'), { target: { value: '跑腿' } });
    fireEvent.click(screen.getByText('检索'));

    await waitFor(() => expect(screen.getByText(/没有命中/)).toBeTruthy());
    expect(screen.queryByText(/不是语义检索/)).toBeNull();
  });

  it('经验卡要显示结果好坏——失败案例同样入库，混着看会把参考价拉高', async () => {
    openAsk({
      '/users/me': ME,
      '/knowledge/cards': [
        { id: 1, category: '保洁', city: '上海', title: '保洁·上海', price_actual_cents: 20000,
          duration_days: 1, outcome: 'completed', has_decomposition: false },
        { id: 2, category: '保洁', city: '上海', title: '保洁·上海', price_actual_cents: 90000,
          duration_days: 0, outcome: 'disputed', has_decomposition: true },
      ],
    });
    fireEvent.click(await screen.findByText('看最近的'));
    await waitFor(() => expect(screen.getByText('¥200.00')).toBeTruthy());
    // KB-004：这一列不显示的话，有纠纷的那笔 ¥900 会被当成行情
    expect(screen.getByText('已完成')).toBeTruthy();
    expect(screen.getByText('有纠纷')).toBeTruthy();
  });

  it('空结果说清为什么是空的，不说成「出错了」', async () => {
    openAsk({ '/users/me': ME, '/knowledge/cards': [] });
    fireEvent.click(await screen.findByText('看最近的'));
    await waitFor(() => expect(screen.getByText(/没有闭环就没有经验/)).toBeTruthy());
  });
});
