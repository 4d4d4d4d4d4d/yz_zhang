// SCN-172（299 号 spec）App 私聊里写下想伤害自己的话：消息照常发出，只给发送的人显示心理援助热线。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { MessagesScreen } from './MessagesAndInvites';

const HOTLINE = '如果你或身边的人现在有伤害自己的念头，请马上拨打 12356 全国心理援助热线';

function client(reply: Record<string, unknown>, sent: string[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    if (method === 'POST' && path === '/conversations/5/messages') sent.push(JSON.parse(init?.body ?? '{}').content);
    const body = path === '/conversations/5/messages' ? (method === 'POST' ? reply : [])
      : path === '/conversations' ? [{ id: 5, kind: 'direct', task_id: null, participants: [1, 2] }] : {};
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SCN-172 App 私聊里的热线', () => {
  it('服务端给了 support 时显示；普通消息不显示', async () => {
    const sent: string[] = [];
    render(<MessagesScreen client={client({ id: 9, risk_flagged: false, warning: null, support: HOTLINE }, sent)} initialConversationId={5} />);
    fireEvent.changeText(await screen.findByPlaceholderText('说点什么'), '不想活了');
    fireEvent.press(screen.getByText('发送'));
    expect((await screen.findByLabelText('心理援助热线')).props.children).toBe(HOTLINE);
    expect(sent).toEqual(['不想活了']);
  });

  it('普通消息不显示', async () => {
    const sent: string[] = [];
    render(<MessagesScreen client={client({ id: 9, risk_flagged: false, warning: null }, sent)} initialConversationId={5} />);
    fireEvent.changeText(await screen.findByPlaceholderText('说点什么'), '明天见');
    fireEvent.press(screen.getByText('发送'));
    await waitFor(() => expect(sent).toEqual(['明天见']));
    expect(screen.queryByLabelText('心理援助热线')).toBeNull();
  });
});
