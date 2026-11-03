// AI-DEC-001 App「说一句话发单」（366 号 spec）：答过的带上再问；问清后把草稿当发布页模板交出去；被拦下说清原因；畸形响应不白屏。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { ClarifyScreen } from './clarify';
import { SUB_SCREEN_LABEL } from './TeamCoopDev';

type Call = { method: string; path: string; body: Record<string, unknown> | null };
const DRAFT = { title: '家里要打扫一下', description: '家里要打扫一下\n地点：上海浦东', category: '保洁', is_remote: false, budget_cents: null, on_behalf_hint: true };
function makeClient(reply: (body: Record<string, unknown>) => unknown, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = init?.body ? JSON.parse(init.body) : null;
    calls.push({ method: init?.method ?? 'GET', path, body });
    return { ok: true, status: 200, text: async () => JSON.stringify(reply(body ?? {})) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('AI-DEC-001 App 说一句话发单', () => {
  it('「我的」里有入口', () => {
    expect(SUB_SCREEN_LABEL.clarify).toContain('说一句话发单');
  });

  it('答过的带上再问，问清后交出发布页模板；说到家里人提示「替别人发」', async () => {
    const calls: Call[] = [];
    const onUse = jest.fn();
    const client = makeClient((body) => (Object.keys((body.answers as object) || {}).length
      ? { questions: [], draft: DRAFT, ready: true, blocked: null, remaining_required: 0 }
      : { questions: [{ key: 'where', ask: '在哪里做？', required: true, options: [] }], draft: { ...DRAFT, description: '家里要打扫一下' },
          ready: false, blocked: null, remaining_required: 1 }), calls);
    render(<ClarifyScreen client={client} onUse={onUse} />);
    fireEvent.changeText(screen.getByLabelText('你要办什么事'), '家里要打扫一下');
    fireEvent.press(screen.getByText('开始'));
    expect(await screen.findByText('还差 1 件要问清楚')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('在哪里做？'), '上海浦东');
    fireEvent.press(screen.getByText('回答'));
    await waitFor(() => expect(calls.length).toBe(2));
    expect(calls[1].body).toEqual({ text: '家里要打扫一下', answers: { where: '上海浦东' }, category: '' });
    expect(await screen.findByText(/替别人发/)).toBeTruthy();
    fireEvent.press(screen.getByText('带到发布页'));
    expect(onUse).toHaveBeenCalledWith(expect.objectContaining({ title: '家里要打扫一下', category: '保洁', description: DRAFT.description }));
  });

  it('被拦下说清原因、不给「带到发布页」；畸形响应说稍后再试', async () => {
    // 拦截响应即使带了问题（服务端不会，但客户端不能依赖这一点），也不给「回答」
    render(<ClarifyScreen client={makeClient(() => ({ questions: [{ key: 'where', ask: '在哪里做？', required: true, options: [] }], draft: DRAFT, ready: false,
      blocked: { code: 'errand_restricted', message: '平台不承接代开处方药' }, remaining_required: 3 }))} onUse={jest.fn()} />);
    fireEvent.changeText(screen.getByLabelText('你要办什么事'), '代开安眠药');
    fireEvent.press(screen.getByText('开始'));
    expect(await screen.findByText('平台不承接代开处方药')).toBeTruthy();
    expect(screen.queryByText('带到发布页')).toBeNull();
    expect(screen.queryByText('回答')).toBeNull();
  });

  it('响应畸形不白屏', async () => {
    render(<ClarifyScreen client={makeClient(() => ({ nope: 1 }))} onUse={jest.fn()} />);
    fireEvent.changeText(screen.getByLabelText('你要办什么事'), '家里要打扫一下');
    fireEvent.press(screen.getByText('开始'));
    expect(await screen.findByText('助手暂时没回上来，请稍后再试')).toBeTruthy();
  });
});
