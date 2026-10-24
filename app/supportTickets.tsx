// CS-013 / ESCA-051 App 上的「我的工单」（150 号 spec）：此前 App 上提不了工单、也看不到客服回复；
// 现在能提、能看回复，并且看得到有没有人接手、是否已超时升级（看不到接手的是哪位管理员）。
import { ticketReplyNotice, apiErrorText, formatDateTime, type MyTicket, type PlatformClient, type TicketCategory, type UrgentHint } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, Image, Modal, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';

// ESCA-057（227 号 spec）截图：一条最多 4 张（与服务端一致），每张不超过 2MB
const MAX_TICKET_IMAGES = 4;
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

/** 从相册选一张截图上传，返回 url；没权限、太大、读不到时返回说明（给人看的那句） */
export async function pickScreenshot(client: PlatformClient): Promise<{ url?: string; error?: string }> {
  const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (perm.status !== 'granted') return { error: '没有相册权限，请在系统设置里允许后重试' };
  const r = await ImagePicker.launchImageLibraryAsync({ quality: 0.6, base64: true });
  if (r.canceled) return {};
  const asset = r.assets?.[0];
  if (!asset?.base64) return { error: '读不到图片数据，请换一张' };
  if ((asset.base64.length / 4) * 3 > MAX_IMAGE_BYTES) return { error: '这张图超过 2MB，请裁小一些再选' };
  const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
  return { url: up.url };
}

// ESCA-063（233 号 spec）截图的地址是站内路径（/api/v1/files/…），拼上 API 地址才能显示
const DEFAULT_BASE = (process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export function shotUri(url: string, baseUrl: string): string {
  return url.startsWith('http') ? url : `${baseUrl}${url}`;
}

/** ESCA-063 「看截图 1」「看截图 2」：点开全屏看大图，点「关闭」回来 */
export function TicketShots({ urls, baseUrl, label }: { urls?: string[]; baseUrl: string; label: string }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!urls?.length) return null;
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {urls.map((u, i) => (
        <TouchableOpacity key={u} accessibilityLabel={`${label}：看截图 ${i + 1}`} onPress={() => setOpen(u)}>
          <Text style={{ color: '#2563eb' }}>看截图 {i + 1}</Text>
        </TouchableOpacity>
      ))}
      <Modal visible={open !== null} transparent animationType="fade" onRequestClose={() => setOpen(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'center', padding: 12, gap: 12 }}>
          {open !== null && (
            <Image accessibilityLabel="截图大图" source={{ uri: shotUri(open, baseUrl) }}
                   style={{ width: '100%', height: '80%' }} resizeMode="contain" />
          )}
          <Button title="关闭" onPress={() => setOpen(null)} />
        </View>
      </Modal>
    </View>
  );
}

/** 工单里「附 N 张截图」（ESCA-063 起旁边有「看截图」可以点开大图） */
export function imagesNote(urls?: string[]): string {
  return urls?.length ? `附 ${urls.length} 张截图` : '';
}

export function ticketProgress(t: MyTicket): string {
  if (t.status !== 'open') return '';
  const who = (t.claimed ? '已有客服接手' : '排队等待客服接手') + (t.first_responded ? ' · 客服已回复' : '');
  const level = t.escalation_level >= 2 ? ' · 已升级给客服主管跟进' : t.escalation_level === 1 ? ' · 已超时，已催办' : '';
  return `${who} · 已等 ${t.waited_hours} 小时（承诺 ${t.sla_hours} 小时内处理）${level}`;
}

const STATUS: Record<string, string> = { open: '处理中', resolved: '已处理', escalated: '已转纠纷' };

export function SupportTicketsScreen({ client, baseUrl = DEFAULT_BASE }: { client: PlatformClient; baseUrl?: string }) {
  const [rows, setRows] = useState<MyTicket[]>([]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  // ESCA-052（172 号 spec）资金、账号类加急，时限更短
  const [category, setCategory] = useState<TicketCategory>('general');
  const [images, setImages] = useState<string[]>([]);
  // ESCA-060（229 号 spec）选加急类别时，若最近自选加急多数被改回一般，提示一句（不拦）
  const [urgentHint, setUrgentHint] = useState<UrgentHint | null>(null);
  useEffect(() => { client.myUrgentHint().then(setUrgentHint).catch(() => setUrgentHint(null)); }, [client]);
  const [draftImages, setDraftImages] = useState<Record<number, string[]>>({});
  async function addShot(onUrl: (u: string) => void) {
    setError('');
    try {
      const r = await pickScreenshot(client);
      if (r.error) setError(r.error);
      if (r.url) onUrl(r.url);
    } catch (e) { setError(apiErrorText(e)); }
  }
  const load = useCallback(async () => {
    try { setRows(await client.myTickets()); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 12 }}>
      <View style={s.card} accessibilityLabel="提交工单">
        <Text style={s.title}>找客服</Text>
        <TextInput style={s.input} accessibilityLabel="问题概括" placeholder="问题一句话概括" value={subject} onChangeText={setSubject} />
        <TextInput style={s.input} accessibilityLabel="详细描述" placeholder="详细描述（越具体越快解决）" multiline value={body} onChangeText={setBody} />
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {([['general', '一般'], ['funds', '资金 · 加急'], ['account', '账号 · 加急']] as [TicketCategory, string][]).map(([k, label]) => (
            <Button key={k} title={category === k ? `✓ ${label}` : label} onPress={() => setCategory(k)} />
          ))}
        </View>
        {category !== 'general' && !!urgentHint?.message && <Text style={s.warn}>{urgentHint.message}</Text>}
        {images.length < MAX_TICKET_IMAGES && (
          <Button title={images.length ? `再加一张截图（已附 ${images.length} 张）` : '附截图（截之前遮住卡号、证件号）'}
                  onPress={() => void addShot((u) => setImages((p) => [...p, u]))} />
        )}
        <Button title="提交工单" disabled={subject.trim().length < 2} onPress={() => void (async () => {
          setError(''); setNotice('');
          try {
            const r = await client.createTicket(subject.trim(), body.trim(), category === 'general' ? undefined : category, images);
            setSubject(''); setBody(''); setCategory('general'); setImages([]);
            setNotice('已提交。客服回复会发站内信，也会显示在下面。' + (r.priority_note ? `\n${r.priority_note}` : ''));
            await load();
          } catch (e) { setError(apiErrorText(e)); }
        })()} />
        {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
        {!!error && <Text style={s.error}>{error}</Text>}
      </View>
      <Text style={s.title}>我的工单（{rows.length}）</Text>
      {rows.length === 0 && <Text style={s.muted}>还没有工单。</Text>}
      {rows.map((t) => (
        <View key={t.id} style={s.card} accessibilityLabel={`工单 ${t.id}`}>
          <Text style={{ fontWeight: '600' }}>{t.subject} · {STATUS[t.status] || t.status}{t.priority === 'urgent' ? ' · 加急' : ''}</Text>
          {!!t.body && <Text style={s.muted}>{t.body}</Text>}
          {!!imagesNote(t.images) && <Text style={s.muted}>{imagesNote(t.images)}</Text>}
          <TicketShots urls={t.images} baseUrl={baseUrl} label={`工单 ${t.id}`} />
          <Text style={s.muted}>{formatDateTime(t.created_at)}</Text>
          {!!t.reply && <Text>客服回复：{t.reply}</Text>}
          {/* ESCA-053（157 号 spec）往来记录：多于一条时把之前的也列出来 */}
          {/* ESCA-062（231 号 spec）客服回复附了图的，也把往来列出来 */}
          {((t.replies?.length ?? 0) > 1 || (t.replies ?? []).some((x) => !x.is_staff || (x.images?.length ?? 0) > 0)) && t.replies.map((x, i) => (
            <View key={i}>
              <Text style={s.muted}>{x.is_staff ? '客服' : '我'}（{formatDateTime(x.created_at)}）：{x.body}{imagesNote(x.images) ? `（${imagesNote(x.images)}）` : ''}</Text>
              <TicketShots urls={x.images} baseUrl={baseUrl} label={`工单 ${t.id} 第 ${i + 1} 条`} />
            </View>
          ))}
          {!!ticketProgress(t) && <Text style={s.muted}>{ticketProgress(t)}</Text>}
          {/* ESCA-056（166 号 spec）补充材料不用再开一张；已结的 7 天内补充会重新打开 */}
          {(t.status === 'open' || t.status === 'resolved') && (
            <>
              <TextInput style={s.input} accessibilityLabel={`补充工单 ${t.id}`} multiline value={drafts[t.id] ?? ''}
                         placeholder={t.status === 'resolved' ? '没解决？补充说明会重新打开这张工单' : '补充说明或材料'}
                         onChangeText={(v) => setDrafts({ ...drafts, [t.id]: v })} />
              {(draftImages[t.id] ?? []).length < MAX_TICKET_IMAGES && (
                <Button title={(draftImages[t.id] ?? []).length ? `再加一张截图（已附 ${(draftImages[t.id] ?? []).length} 张）` : '附截图'}
                        onPress={() => void addShot((u) => setDraftImages((p) => ({ ...p, [t.id]: [...(p[t.id] ?? []), u] })))} />
              )}
              <Button title="补充" disabled={!(drafts[t.id] ?? '').trim()} onPress={() => void (async () => {
                setError(''); setNotice('');
                try {
                  const r = await client.replyMyTicket(t.id, (drafts[t.id] ?? '').trim(), draftImages[t.id]);
                  setDrafts({ ...drafts, [t.id]: '' });
                  setDraftImages({ ...draftImages, [t.id]: [] });
                  setNotice(ticketReplyNotice(r));
                  await load();
                } catch (e) { setError(apiErrorText(e)); }
              })()} />
            </>
          )}
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
  warn: { color: '#b45309' },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 6, padding: 8 },
});
