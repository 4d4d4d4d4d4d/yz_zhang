// SBX-100 隐私沙箱（128 号 spec）：开关、本机助手、原文不出设备、同步前脱敏并由人确认；管理端模型目录的四眼。
import { PlatformClient } from '@platform/core';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SandboxModelsAdmin } from './AdminSandbox';
import Sandbox from './pages/Sandbox';
import { AppProvider, useApp } from './store';

type Call = { method: string; path: string; body?: unknown };
const OFF = { enabled: false, since: null, blocked_endpoints: 14, note: '开着时：摘要、拆清单……原文不发到云端' };
const ON = { ...OFF, enabled: true, since: '2026-10-14T08:00:00Z' };
const MODEL = {
  id: 1, key: 'qwen2.5-0.5b-q4km', name: 'Qwen2.5 0.5B Instruct', family: 'qwen2.5', params_b: 0.5, quant: 'Q4_K_M', file_format: 'gguf',
  size_mb: 400, sha256: 'a'.repeat(64), url: 'https://example.org/q.gguf', license: 'Apache-2.0', min_ram_gb: 3, languages: ['zh'],
  skills: ['summarize'], note: '', published_at: '2026-10-14T00:00:00Z',
};

function mount(node: React.ReactNode, routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter><AppProvider client={client}>{node}</AppProvider></MemoryRouter>);
}
afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

describe('SBX-100 隐私沙箱（Web）', () => {
  it('打开沙箱：先在本机生效再告诉服务端；关闭：服务端成功后才在本机关', async () => {
    const calls: Call[] = [];
    let state: unknown = OFF;
    const routes: Record<string, unknown> = { '/sandbox/models': { items: [MODEL], note: '模型文件不经平台' } };
    Object.defineProperty(routes, 'GET /users/me/sandbox', { enumerable: true, get: () => state });
    Object.defineProperty(routes, 'PUT /users/me/sandbox', { enumerable: true, get: () => { state = state === OFF ? ON : OFF; return state; } });
    mount(<Sandbox />, routes, calls);
    fireEvent.click(await screen.findByRole('button', { name: '打开沙箱' }));
    await screen.findByText('隐私沙箱已打开：助手的活在本机做');
    expect(localStorage.getItem('sandbox')).toBe('1');
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ enabled: true });
    expect(screen.getByLabelText('沙箱开关').textContent).toContain('14 类云端助手接口被拦下');
    expect(screen.getByLabelText('端侧模型').textContent).toContain('Qwen2.5 0.5B Instruct');
    expect(screen.getByLabelText('浏览器端模型').textContent).toContain('没有 WebGPU');
    fireEvent.click(screen.getByRole('button', { name: '关闭沙箱' }));
    await screen.findByText('隐私沙箱已关闭：可以用云端助手了');
    expect(localStorage.getItem('sandbox')).toBeNull();
  });

  it('本机助手处理原文；原文一个字也不发出去；同步的是脱敏后的、且要人勾选确认', async () => {
    const calls: Call[] = [];
    mount(<Sandbox />, { '/users/me/sandbox': ON, '/sandbox/models': { items: [], note: '' }, 'POST /notebook/notes': { id: 1 } }, calls);
    const raw = '周会纪要。需要联系 13812345678 确认上门时间。记得带发票。';
    fireEvent.change(await screen.findByLabelText('本机内容'), { target: { value: raw } });
    fireEvent.click(screen.getByRole('button', { name: '抽出待办' }));
    const out = await screen.findByLabelText('本机结果');
    expect(out.textContent).toContain('需要联系 13812345678 确认上门时间');
    expect(out.textContent).toContain('不是模型');
    const preview = screen.getByLabelText('同步前脱敏');
    expect(preview.textContent).toContain('138****5678');
    expect(preview.textContent).toContain('遮掉了：手机号 1 处');
    const send = screen.getByRole('button', { name: '放进我的知识库' }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/我看过了/));
    fireEvent.click(send);
    await screen.findByText('脱敏后的结果已放进你的知识库');
    const sent = calls.find((c) => c.method === 'POST' && c.path === '/notebook/notes')?.body as { body: string };
    expect(sent.body).toContain('138****5678');
    expect(JSON.stringify(calls)).not.toContain('13812345678');
    // 存在本机：进 localStorage，不发请求
    const before = calls.length;
    fireEvent.click(screen.getByRole('button', { name: '存在本机' }));
    expect(JSON.parse(localStorage.getItem('sandbox.notes') || '[]')[0].text).toBe(raw);
    expect(calls.length).toBe(before);
    expect(screen.getByLabelText('本机笔记').textContent).toContain('本机笔记（1）');
  });

  it('一句话指令碰到红线（转账、发布、对外发送）就不做', async () => {
    mount(<Sandbox />, { '/users/me/sandbox': ON, '/sandbox/models': { items: [], note: '' } }, []);
    fireEvent.change(await screen.findByLabelText('本机内容'), { target: { value: '尾款 3000 元' } });
    fireEvent.change(screen.getByLabelText('一句话指令'), { target: { value: '帮我把尾款转账给他' } });
    fireEvent.click(screen.getByRole('button', { name: '让本机助手做' }));
    expect((await screen.findByText(/沙箱里不做/)).textContent).toContain('本人在联网模式下确认');
  });

  it('默认客户端（store 建的）在沙箱开着时不把原文发给云端 AI', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, text: async () => '{}' }));
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem('sandbox', '1');
    let client: PlatformClient | null = null;
    function Grab() { client = useApp().client; return null; }
    render(<MemoryRouter><AppProvider><Grab /></AppProvider></MemoryRouter>);
    await waitFor(() => expect(client).not.toBeNull());
    fetchMock.mockClear();
    await act(async () => {
      await expect(client!.askNotebook('我的合同里写了什么')).rejects.toMatchObject({ code: 'sandbox_cloud_ai_blocked' });
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('SBX-106 端侧模型目录（管理端）', () => {
  it('登记为草稿；自己登记的没有「上架」按钮；别人登记的可以上架', async () => {
    const calls: Call[] = [];
    localStorage.setItem('token', 'tok');
    const rows = [
      { ...MODEL, id: 1, status: 'draft', created_by: 0, reviewed_by: null, retired_reason: '', created_at: '2026-10-14T00:00:00Z' },
      { ...MODEL, id: 2, key: 'mine', name: '我登记的', status: 'draft', created_by: 2, reviewed_by: null, retired_reason: '', created_at: '2026-10-14T00:00:00Z' },
    ];
    mount(<SandboxModelsAdmin />, {
      '/users/me': { id: 2, nickname: '运营', is_admin: true }, '/admin/sandbox/models': rows,
      'POST /admin/sandbox/models': rows[1], 'POST /admin/sandbox/models/1/publish': { ...rows[0], status: 'published' },
    }, calls);
    const table = await screen.findByLabelText('端侧模型目录');
    await waitFor(() => expect(table.textContent).toContain('我登记的'));
    await waitFor(() => expect(screen.getAllByRole('button', { name: '上架' })).toHaveLength(1));
    fireEvent.change(screen.getByLabelText('模型标识'), { target: { value: 'qwen-1.5b' } });
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'Qwen 1.5B' } });
    fireEvent.change(screen.getByLabelText('sha256'), { target: { value: 'b'.repeat(64) } });
    fireEvent.click(screen.getByRole('button', { name: '登记' }));
    await screen.findByText(/已登记为草稿/);
    expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/sandbox/models')?.body)
      .toMatchObject({ key: 'qwen-1.5b', name: 'Qwen 1.5B', sha256: 'b'.repeat(64), skills: ['summarize', 'todos', 'checklist'] });
    fireEvent.click(screen.getByRole('button', { name: '上架' }));
    await screen.findByText('已上架：Qwen2.5 0.5B Instruct');
  });
});
