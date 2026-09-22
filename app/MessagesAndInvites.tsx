// APP-067/068 App 的站内信与任务邀约（68 号 spec）。
//
// 两条都是「服务端早就有、手机上一直没有」：
//
// - 会话：任务会话在**合约托管成功**时才自动建（IM-002），也就是说
//   **钱已经托管了，两个人才开始说得上话**；成交前要问「你几点能到」
//   只能靠任务描述。`openDirect` 建好了，此前**没有任何一个端调用过它**。
// - 邀约：服务端**会发**「收到任务邀约」这条通知，而 `acceptInvitation`
//   在 App 上不存在——又一条「通知把人叫来了，他点进去无路可走」。
import {
  apiErrorText, fmtYuan,
  type InvitationItem, type Message, type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type ConversationRow = Awaited<ReturnType<PlatformClient['conversations']>>[number];

export function MessagesScreen({ client }: { client: PlatformClient }) {
  const [convs, setConvs] = useState<ConversationRow[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [unread, setUnread] = useState(0);
  const [peer, setPeer] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setConvs(await client.conversations().catch(() => []));
    setUnread(await client.imUnreadCount().then((r) => r.unread).catch(() => 0));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  if (open !== null) {
    return <Thread client={client} convId={open} onBack={() => { setOpen(null); void load(); }} />;
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 10, paddingBottom: 24 }}>
      <Text style={s.title}>消息{unread > 0 ? `（${unread} 条未读）` : ''}</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {convs.length === 0 && <Text style={s.muted}>还没有会话。</Text>}
      {convs.map((c) => (
        <TouchableOpacity key={c.id} style={s.card} onPress={() => setOpen(c.id)}>
          <Text style={s.cardTitle}>
            {c.kind === 'task' ? `任务会话 #${c.task_id}` : `会话 #${c.id}`}
          </Text>
          <Text style={s.muted}>
            {c.last_message?.content || '（暂无消息）'}
            {c.unread_count > 0 ? ` · ${c.unread_count} 条未读` : ''}
          </Text>
        </TouchableOpacity>
      ))}

      {/* IM-020 成交前也要说得上话。此前只有托管成功才会自动建会话， */}
      {/* 而「你几点能到」「要不要带工具」全发生在托管之前。 */}
      <Text style={s.cardTitle}>发起会话</Text>
      <TextInput style={s.input} keyboardType="numeric" value={peer} onChangeText={setPeer}
                 placeholder="对方用户 ID" />
      <Button title="开始聊" onPress={async () => {
        setError('');
        try {
          const conv = await client.openDirect(Number(peer));
          setPeer('');
          await load();
          setOpen(conv.id);
        } catch (e) {
          // 拉黑、对方不存在等：服务端的理由原样显示
          setError(apiErrorText(e));
        }
      }} />
    </ScrollView>
  );
}

function Thread({ client, convId, onBack }: {
  client: PlatformClient; convId: number; onBack: () => void;
}) {
  const [rows, setRows] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.messages(convId).catch(() => []));
    // IM-005 进来就把已读位点推到最新，未读数才不会一直挂着
    await client.markConversationRead(convId).catch(() => undefined);
  }, [client, convId]);
  useEffect(() => { void load(); }, [load]);

  return (
    <ScrollView contentContainerStyle={{ gap: 8, paddingBottom: 24 }}>
      <TouchableOpacity onPress={onBack}><Text style={s.link}>← 返回消息列表</Text></TouchableOpacity>
      {rows.map((m) => (
        <View key={m.id} style={s.card}>
          <Text style={s.muted}>#{m.sender_id}</Text>
          <Text>{m.content}</Text>
          {/* IM-006 命中风控的消息带标记：教育型提示，不拦截 */}
          {m.risk_flagged && <Text style={s.error}>⚠️ 疑似站外引导</Text>}
          {/* IM-004 服务端给了 2 分钟撤回窗口，此前**没有任何端能点**。
              发错人、手滑把手机号发出去，都收不回来。
              过期由服务端判并给理由，客户端不重算那 2 分钟。 */}
          {!m.recalled && (
            <Button title="撤回" color="#6b7280" onPress={async () => {
              setError('');
              try {
                await client.recallMessage(m.id);
                await load();
              } catch (e) {
                setError(apiErrorText(e));
              }
            }} />
          )}
        </View>
      ))}
      <TextInput style={s.input} value={text} onChangeText={setText} placeholder="说点什么" />
      <Button title="发送" onPress={async () => {
        setError(''); setWarning(null);
        try {
          const r = await client.sendMessage(convId, text);
          setText('');
          // IM-006 服务端的提醒原样显示，不自己编一句
          setWarning(r.warning);
          await load();
        } catch (e) {
          setError(apiErrorText(e));
        }
      }} />
      {!!warning && <Text style={s.error}>⚠️ {warning}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </ScrollView>
  );
}

/** APP-068 任务邀约。服务端会发「收到任务邀约」这条通知，
 *  而此前 App 上没有任何地方能看到它、更别说接受。 */
export function InvitationsScreen({ client }: { client: PlatformClient }) {
  const [rows, setRows] = useState<InvitationItem[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setRows(await client.myInvitations().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError(''); setNotice('');
    try {
      await fn();
      await load();
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 10, paddingBottom: 24 }}>
      <Text style={s.title}>收到的邀约</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!!notice && <Text style={s.muted}>{notice}</Text>}
      {rows.length === 0 && <Text style={s.muted}>还没有人邀请你接单。</Text>}
      {rows.map((iv) => (
        <View key={iv.id} style={s.card}>
          <Text style={s.cardTitle}>{iv.task_title} · {fmtYuan(iv.budget_cents)}</Text>
          <Text style={s.muted}>{iv.message || '（无留言）'} · {iv.status}</Text>
          {iv.status === 'pending' && (
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
              <Button title="接受" onPress={() => act(async () => {
                const r = await client.acceptInvitation(iv.id);
                // 接受即成交：直接告诉他下一步在哪，别让他自己找
                setNotice(`已接受，合约 #${r.contract_id} 已生成，去任务页签署并等待托管`);
              })} />
              <Button title="谢绝" color="#6b7280"
                      onPress={() => act(() => client.declineInvitation(iv.id))} />
            </View>
          )}
        </View>
      ))}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  title: { fontSize: 20, fontWeight: '700', color: '#2f6fed' },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#dc2626' },
  link: { color: '#2f6fed', paddingVertical: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
});
