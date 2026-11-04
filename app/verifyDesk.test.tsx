// VER-053 App 核验台（381 号 spec）：看单、接单、提交结论、被点名时拒绝；畸形响应不白屏。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SubScreenHost } from './TeamCoopDev';

type Call = { method: string; path: string; body: unknown };
const order = (over: Record<string, unknown> = {}) => ({ id: 3, task_id: 7, status: 'open', trigger: 'designated', fee_cents: 3000,
  payer_id: 5, verifier_id: null, designated_verifier_id: 2, outcome: '', comment: '', revised_output: '', criteria_results: [],
  deadline: null, created_at: null, category: '软件开发', task_title: '写一篇接口文档', claimable: true, reason: '', ...over });
const DETAIL = { ...order(), status: 'claimed', verifier_id: 2, task_description: '把十个接口写清楚',
  acceptance_criteria: [{ text: '包含全部接口', kind: 'auto' }], agent_output: '初稿……', agent_confidence_bps: 6200,
  agent_criteria_results: [{ text: '包含全部接口', kind: 'auto', passed: false }] };

function open(routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[`${method} ${path}`] ?? routes[path];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  render(<SubScreenHost client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} screen="verify" onBack={() => undefined} />);
  return calls;
}

describe('VER-053 App 核验台', () => {
  it('列出可接的单与来路；不能接的写原因、按钮点不动', async () => {
    open({ '/users/me': { id: 2 }, '/verification-orders': [order(), order({ id: 4, trigger: 'escalation', designated_verifier_id: null,
      claimable: false, reason: '需有「软件开发」类目的完成记录', task_title: '另一单' })] });
    expect(await screen.findByText('发布方点名请你核验（发布方付费）')).toBeTruthy();
    expect(screen.getByText('需有「软件开发」类目的完成记录')).toBeTruthy();
    expect(screen.getByText('助理置信度不足，自动升级（平台付费）')).toBeTruthy();
  });

  it('被点名的单可以当场拒绝；点名别人的、平台派的没有拒绝按钮', async () => {
    const calls = open({ '/users/me': { id: 2 }, '/verification-orders': [order(), order({ id: 4, designated_verifier_id: 9, task_title: '另一单' })],
      'POST /verification-orders/3/decline': { ...order(), status: 'cancelled' } });
    await screen.findByText('写一篇接口文档');
    await waitFor(() => expect(screen.getAllByText('不方便，拒绝').length).toBe(1));
    fireEvent.press(screen.getByText('不方便，拒绝'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/verification-orders/3/decline')).toBe(true));
    expect(await screen.findByText('已拒绝，核验费已退回给发布方')).toBeTruthy();
  });

  it('接下后看 AI 产出与自报置信度，写修正稿提交结论；理由太空当场提醒', async () => {
    const calls = open({ '/users/me': { id: 2 }, '/verification-orders': [order()], 'POST /verification-orders/3/claim': DETAIL,
      '/verification-orders/3': DETAIL, 'POST /verification-orders/3/outcome': { outcome: 'revised', unblocked: true, delivered: true } });
    fireEvent.press(await screen.findByText('接下'));
    expect(await screen.findByText('助理自报置信度 62.0%（自报值，仅供参考）')).toBeTruthy();
    expect(screen.getByText('✗ 包含全部接口')).toBeTruthy();
    fireEvent.press(screen.getByText('○ 已修正'));
    fireEvent.changeText(screen.getByPlaceholderText('哪里不对、要怎么改（也会成为下一单的经验）'), '不行');
    expect(screen.getByTestId('vague-lesson')).toBeTruthy();
    fireEvent.changeText(screen.getByPlaceholderText('哪里不对、要怎么改（也会成为下一单的经验）'), '漏了退款接口和分页参数的说明，已补上并按模板重排');
    fireEvent.changeText(screen.getByPlaceholderText('修正稿正文（它会成为交付物）'), '完整的接口文档……');
    fireEvent.press(screen.getByText('提交结论'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/verification-orders/3/outcome')).toBe(true));
    expect(calls.find((c) => c.path === '/verification-orders/3/outcome')!.body).toEqual({
      outcome: 'revised', comment: '漏了退款接口和分页参数的说明，已补上并按模板重排', revised_output: '完整的接口文档……' });
    expect(await screen.findByText('结论已提交')).toBeTruthy();
  });

  it('列表响应畸形：不白屏，说没有单', async () => {
    open({ '/users/me': { id: 2 }, '/verification-orders': { oops: true } });
    expect(await screen.findByText('当前没有待核验的单。')).toBeTruthy();
  });
});
