// SCN-156（278 号 spec）App 任务详情：已完成的单发单人才看到「允许展示这一单」，点了授权；已授权的显示「撤回展示授权」。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { ShowcaseConsentBlock, canGrantShowcase } from './showcase';

function makeClient(calls: Array<{ method: string; path: string }>) {
  const fetchImpl = (async (url: string, init?: { method?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    calls.push({ method: init?.method ?? 'GET', path });
    return { ok: true, status: 200, text: async () => JSON.stringify({ task_id: 60, showcase_consent_at: init?.method === 'POST' ? '2026-10-23T00:00:00Z' : null }) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const T = (extra: Partial<Task>) => ({ id: 60, creator_id: 9, executor_id: 3, status: 'completed', ...extra }) as Task;

describe('SCN-156 App 作品展示授权', () => {
  it('只有已完成单的发单人能授权', () => {
    expect(canGrantShowcase(T({}), 9)).toBe(true);
    expect(canGrantShowcase(T({}), 3)).toBe(false);
    expect(canGrantShowcase(T({ status: 'in_progress' }), 9)).toBe(false);
    expect(canGrantShowcase(T({ executor_id: null }), 9)).toBe(false);
  });

  it('没授权时点「允许展示这一单」；已授权时点「撤回展示授权」', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    const changed = jest.fn();
    const { rerender } = render(<ShowcaseConsentBlock client={makeClient(calls)} task={T({})} onChanged={changed} />);
    fireEvent.press(screen.getByText('允许展示这一单'));
    await waitFor(() => expect(calls).toEqual([{ method: 'POST', path: '/tasks/60/showcase-consent' }]));
    expect(await screen.findByText(/已允许/)).toBeTruthy();
    expect(changed).toHaveBeenCalled();
    rerender(<ShowcaseConsentBlock client={makeClient(calls)} task={T({ showcase_consent_at: '2026-10-23T00:00:00Z' })} onChanged={changed} />);
    fireEvent.press(screen.getByText('撤回展示授权'));
    await waitFor(() => expect(calls[1]).toEqual({ method: 'DELETE', path: '/tasks/60/showcase-consent' }));
  });
});
