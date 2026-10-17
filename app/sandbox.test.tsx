// SBX-100 隐私沙箱在 App 上的行为（128 号 spec）：开关、本机助手、原文不出手机、同步前脱敏并由人确认、端侧模型注入。
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type LocalModel } from '@platform/core';
import { SandboxScreen } from './sandbox';
import { isSandbox, setLocalModel, setSandboxLocal } from './sandboxState';

type Call = { method: string; path: string; body?: unknown };
const OFF = { enabled: false, since: null, blocked_endpoints: 14, note: '开着时……原文不发到云端' };
const ON = { ...OFF, enabled: true, since: '2026-10-14T08:00:00Z' };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl, sandbox: isSandbox });
}
afterEach(async () => { await AsyncStorage.clear(); await setSandboxLocal(false); setLocalModel(null); });

describe('SBX-100 App 上的隐私沙箱', () => {
  it('打开开关：本机先生效、服务端记住；之后客户端拦下云端 AI 请求', async () => {
    const calls: Call[] = [];
    let state: unknown = OFF;
    const routes: Record<string, unknown> = { '/sandbox/models': { items: [], note: '模型文件不经平台' } };
    Object.defineProperty(routes, 'GET /users/me/sandbox', { enumerable: true, get: () => state });
    Object.defineProperty(routes, 'PUT /users/me/sandbox', { enumerable: true, get: () => { state = ON; return ON; } });
    const client = makeClient(routes, calls);
    render(<SandboxScreen client={client} />);
    await screen.findByText('隐私沙箱关着');
    fireEvent(screen.getByLabelText('隐私沙箱'), 'valueChange', true);
    expect(await screen.findByText('隐私沙箱已打开：助手的活在本机做')).toBeTruthy();
    expect(isSandbox()).toBe(true);
    expect(await AsyncStorage.getItem('sandbox')).toBe('1');
    const before = calls.length;
    await expect(client.legalAsk('我的劳动合同能不能这样写')).rejects.toMatchObject({ code: 'sandbox_cloud_ai_blocked' });
    expect(calls.length).toBe(before);
  });

  it('本机规则处理原文、原文不发出去；同步的是脱敏后的，且要人确认', async () => {
    await setSandboxLocal(true);
    const calls: Call[] = [];
    const client = makeClient({ '/users/me/sandbox': ON, '/sandbox/models': { items: [], note: '' }, 'POST /notebook/notes': { id: 1 } }, calls);
    render(<SandboxScreen client={client} />);
    fireEvent.changeText(await screen.findByLabelText('本机内容'), '需要联系 13812345678 确认时间。记得带发票。');
    fireEvent.press(screen.getByText('抽出待办'));
    expect(await screen.findByText(/不是模型/)).toBeTruthy();
    expect(screen.getByText(/遮掉了：手机号 1 处/)).toBeTruthy();
    fireEvent(screen.getByLabelText('我看过了，可以发到云端'), 'valueChange', true);
    fireEvent.press(screen.getByText('放进我的知识库'));
    expect(await screen.findByText('脱敏后的结果已放进你的知识库')).toBeTruthy();
    const sent = calls.find((c) => c.method === 'POST' && c.path === '/notebook/notes')?.body as { body: string };
    expect(sent.body).toContain('138****5678');
    expect(JSON.stringify(calls)).not.toContain('13812345678');
    fireEvent.press(screen.getByText('存在本机'));
    await waitFor(async () => expect(JSON.parse((await AsyncStorage.getItem('sandbox.notes')) || '[]')).toHaveLength(1));
  });

  it('装了端侧模型就用模型；红线指令不做', async () => {
    const model: LocalModel = { id: 'qwen2.5-0.5b-q4', generate: jest.fn(async () => '- 订场地\n- 发邀请') };
    setLocalModel(model);
    const client = makeClient({ '/users/me/sandbox': ON, '/sandbox/models': { items: [], note: '' } }, []);
    render(<SandboxScreen client={client} />);
    expect(await screen.findByText('端侧模型：qwen2.5-0.5b-q4')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('本机内容'), '办一场分享会');
    fireEvent.press(screen.getByText('拆成清单'));
    expect(await screen.findByText(/本机模型「qwen2.5-0.5b-q4」生成/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('一句话指令'), '直接发布到广场');
    fireEvent.press(screen.getByText('让本机助手做'));
    expect(await screen.findByText(/沙箱里不做/)).toBeTruthy();
  });
});
