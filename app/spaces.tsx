// SPACE-028 原生 App 的个人空间：发现人、看空间、经营自己的门面（88 号 spec）。
//
// 核对表第 5 节把它列为下一阶段第 1 条，Spec 88 的 SPACE-028 写着「尚未实现」。
// 现状是：共享 SDK 四个方法（`discoverSpaces` / `personalSpace` / `ownSpace` /
// `saveSpace`）都已就位，web 有三个页面，而 `app/` 里**一行空间代码都没有**。
//
// 这一版产品的定位是「以独立个体为中心的开放协作网络，每个人有可经营的数字空间」。
// 空间只在网页上存在，等于说这个定位**只对坐在电脑前的人成立**——而要整理作品、
// 随手放上一段视频链接、在见到人之后马上看看对方做过什么，手机才是那个场合。
//
// 这里刻意**不抓外部资源**（与服务端一致）：条目只存标题与 HTTPS 链接，
// 点开用系统浏览器。平台不代理、不嵌入、不抓取——那是 SPACE-020 的事，
// 需要单独的授权与运营评估。
import {
  apiErrorText,
  type Me, type OwnSpace, type PersonalSpace, type PlatformClient,
  type SpaceItem, type SpaceSummary,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import {
  Button, FlatList, Linking, RefreshControl, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';

const KIND_LABEL: Record<SpaceItem['kind'], string> = {
  work: '作品', article: '文章', video: '视频', shop: '小店', live: '直播', service: '服务',
};
const KINDS = Object.keys(KIND_LABEL) as SpaceItem['kind'][];
const THEME_LABEL: Record<OwnSpace['theme'], string> = { clay: '陶土', moss: '苔绿', ink: '墨蓝' };
const THEMES = Object.keys(THEME_LABEL) as OwnSpace['theme'][];
const WHO: Record<PersonalSpace['kind'], string> = {
  person: '独立个体', agent: '智能体', organization: '组织空间',
};
/** 服务端 `items` 上限（SpaceIn.items max_length=24）。本地同样拦一道，
 *  否则用户辛苦填到第 25 条才被整单退回。 */
const MAX_ITEMS = 24;

// ---------------------------------------------------------------- 发现人
export function SpacesDiscoverScreen({ client, onOpen }: {
  client: PlatformClient; onOpen: (userId: number) => void;
}) {
  const [rows, setRows] = useState<SpaceSummary[]>([]);
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState('');
  const [cursor, setCursor] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (query: string, after = 0) => {
    setBusy(true); setError('');
    try {
      const r = await client.discoverSpaces(query, after);
      setRows((old) => (after ? [...old, ...r.items] : r.items));
      setCursor(r.next_cursor);
      setApplied(query);
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }, [client]);
  useEffect(() => { void load(''); }, [load]);

  return (
    <View style={{ flex: 1, gap: 8 }}>
      <View style={styles.searchRow}>
        <TextInput style={[styles.input, { flex: 1 }]} value={q} onChangeText={setQ}
                   placeholder="名字、兴趣，或一种可能…"
                   onSubmitEditing={() => void load(q)} returnKeyType="search" />
        <TouchableOpacity onPress={() => void load(q)}>
          <Text style={styles.link}>搜索</Text>
        </TouchableOpacity>
      </View>
      {/* SPACE-011 空状态、错误、加载三者分开——合成一句「暂无数据」会把
          「后端挂了」说成「这里还没有人」。 */}
      {!!error && (
        <View style={styles.card}>
          <Text style={styles.error}>{error}</Text>
          <Button title="重试" onPress={() => void load(applied)} />
        </View>
      )}
      <FlatList
        data={rows}
        keyExtractor={(x) => String(x.user_id)}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={() => void load(applied)} />}
        ListEmptyComponent={busy || error ? null : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              {applied ? '还没有找到这个空间' : '第一扇窗口，等你打开'}
            </Text>
            <Text style={styles.muted}>
              {applied ? '试试另一个名字或关键词。' : '放上一件作品、一篇文章，或你正在做的事。'}
            </Text>
          </View>
        )}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => onOpen(item.user_id)}>
            <Text style={styles.cardTitle}>{item.nickname}</Text>
            {!!item.headline && <Text style={styles.muted}>{item.headline}</Text>}
            <Text style={styles.muted}>
              {WHO[item.kind]} · {item.items_count} 个展示
              {item.accepting_orders ? ' · 可接单' : ''}
            </Text>
          </TouchableOpacity>
        )}
        ListFooterComponent={cursor !== null && !error ? (
          <Button title={busy ? '加载中…' : '再认识一些人'} disabled={busy}
                  onPress={() => void load(applied, cursor)} />
        ) : null}
      />
    </View>
  );
}

// ------------------------------------------------------------ 看别人的空间
export function PublicSpaceScreen({ client, userId, onBack, onOpenConversation }: {
  client: PlatformClient; userId: number; onBack: () => void;
  onOpenConversation: (conversationId: number) => void;
}) {
  const [space, setSpace] = useState<PersonalSpace | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setSpace(null); setError('');
    void client.personalSpace(userId)
      .then((s) => { if (live) setSpace(s); })
      .catch((e) => { if (live) setError(apiErrorText(e)); });
    return () => { live = false; };
  }, [client, userId]);

  async function contact() {
    setBusy(true); setError('');
    try {
      const c = await client.openDirect(userId);
      onOpenConversation(c.id);
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 24 }}>
      <TouchableOpacity onPress={onBack}><Text style={styles.link}>← 返回</Text></TouchableOpacity>
      {!!error && <Text style={styles.error}>{error}</Text>}
      {!space && !error && <Text style={styles.muted}>正在打开这个窗口…</Text>}
      {space && (
        <>
          <Text style={styles.title}>{space.nickname}</Text>
          {!!space.headline && <Text style={styles.cardTitle}>{space.headline}</Text>}
          <Text style={styles.muted}>
            {WHO[space.kind]}{space.accepting_orders ? ' · 可接单' : ''}
          </Text>
          {!!space.introduction && <Text>{space.introduction}</Text>}
          {space.items.map((it, i) => (
            <View key={`${it.title}-${i}`} style={styles.card}>
              <Text style={styles.cardTitle}>{KIND_LABEL[it.kind]} · {it.title}</Text>
              {!!it.summary && <Text style={styles.muted}>{it.summary}</Text>}
              {!!it.url && (
                // 外部链接由用户主动点开，平台不代理也不嵌入（SPACE-003）。
                // 把域名显示出来：点开之前他有权知道自己要去哪里。
                <TouchableOpacity onPress={() => void Linking.openURL(it.url)}>
                  <Text style={styles.link}>在外部打开（{hostOf(it.url)}）↗</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
          {!space.items.length && <Text style={styles.muted}>这个空间还没有放上展示内容。</Text>}
          <Button title={busy ? '正在打开会话…' : '发消息'} disabled={busy}
                  onPress={() => void contact()} />
        </>
      )}
    </ScrollView>
  );
}

function hostOf(url: string): string {
  // RN 里没有 URL.hostname 的完全实现可依赖，取两段之间那一截就够显示了
  const m = /^https:\/\/([^/?#]+)/i.exec(url);
  return m ? m[1] : '外部链接';
}

// ------------------------------------------------------------ 我的空间
export function MySpaceScreen({ client, me, onPreview, refreshMe }: {
  client: PlatformClient; me: Me | null;
  onPreview: (userId: number) => void; refreshMe: () => void;
}) {
  const [space, setSpace] = useState<OwnSpace | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError('');
    try {
      setSpace(await client.ownSpace());
    } catch (e) {
      setError(apiErrorText(e));
    }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  function patch(next: Partial<OwnSpace>) {
    setSpace((s) => (s ? { ...s, ...next } : s));
    setNotice('');
  }

  async function save() {
    if (!space) return;
    setBusy(true); setError(''); setNotice('');
    try {
      // 服务端整体替换并要求 revision：保存成功后用返回值覆盖本地，
      // 否则下一次保存会带着旧 revision 撞 409。
      setSpace(await client.saveSpace({
        revision: space.revision, published: space.published,
        headline: space.headline, introduction: space.introduction,
        theme: space.theme, items: space.items,
      }));
      setNotice('已保存');
    } catch (e) {
      // 冲突、隐私未开、缺介绍、机审不通过都走这里，服务端的话原样显示：
      // 它们每一句都说清了该做什么（CLI-064）。
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  /** PROFILE_PRIVATE 的补救。服务端拦住发布时说「请先在账户隐私设置中允许
   *  公开个人资料」——而 App 上此前**没有任何地方能改这一项**，
   *  于是 App 用户永远发不出自己的空间，只能看着那句提示。
   *  这正是 66 号 spec 立的规矩：服务端说「请先 X」，X 就必须在端上有入口。 */
  async function allowPublicProfile() {
    setBusy(true); setError(''); setNotice('');
    try {
      await client.updateMe({ privacy: { profile_public: true } });
      refreshMe();
      await load();
      setNotice('已允许公开个人资料，现在可以发布空间');
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!space) {
    return (
      <View style={{ gap: 12 }}>
        {!!error && <Text style={styles.error}>{error}</Text>}
        <Text style={styles.muted}>{error ? '' : '正在打开我的空间…'}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 32 }}>
      <Text style={styles.title}>我的空间</Text>
      <Text style={styles.muted}>
        {space.published ? '已公开：任何人都能通过链接浏览以下内容' : '未公开：只有你自己看得到'}
      </Text>

      <TextInput style={styles.input} value={space.headline}
                 onChangeText={(t) => patch({ headline: t })}
                 placeholder="一句话介绍（公开前必填）" />
      <TextInput style={[styles.input, { minHeight: 96 }]} multiline value={space.introduction}
                 onChangeText={(t) => patch({ introduction: t })}
                 placeholder="你是谁、做过什么、现在想一起做什么" />

      <Text style={styles.cardTitle}>主题</Text>
      <View style={styles.row}>
        {THEMES.map((t) => (
          <TouchableOpacity key={t} onPress={() => patch({ theme: t })}>
            <Text style={[styles.chip, space.theme === t && styles.chipOn]}>{THEME_LABEL[t]}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.cardTitle}>展示条目（{space.items.length}/{MAX_ITEMS}）</Text>
      {space.items.map((it, i) => (
        <View key={i} style={styles.card}>
          <View style={styles.row}>
            {KINDS.map((k) => (
              <TouchableOpacity key={k} onPress={() => patch({
                items: space.items.map((x, j) => (j === i ? { ...x, kind: k } : x)),
              })}>
                <Text style={[styles.chip, it.kind === k && styles.chipOn]}>{KIND_LABEL[k]}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput style={styles.input} value={it.title} placeholder="标题"
                     onChangeText={(t) => patch({
                       items: space.items.map((x, j) => (j === i ? { ...x, title: t } : x)),
                     })} />
          <TextInput style={styles.input} value={it.summary} placeholder="一句说明（可不填）"
                     onChangeText={(t) => patch({
                       items: space.items.map((x, j) => (j === i ? { ...x, summary: t } : x)),
                     })} />
          {/* 服务端只收完整 HTTPS 地址且不许带登录凭据（SPACE-003）。
              这里把要求写在占位符里，而不是等它 422 回来。 */}
          <TextInput style={styles.input} value={it.url} autoCapitalize="none"
                     placeholder="https:// 开头的外部链接（可不填）"
                     onChangeText={(t) => patch({
                       items: space.items.map((x, j) => (j === i ? { ...x, url: t } : x)),
                     })} />
          <TouchableOpacity onPress={() => patch({ items: space.items.filter((_, j) => j !== i) })}>
            <Text style={styles.link}>删除这一条</Text>
          </TouchableOpacity>
        </View>
      ))}
      {space.items.length < MAX_ITEMS && (
        <Button title="添加一条展示" onPress={() => patch({
          items: [...space.items, { title: '', kind: 'work', summary: '', url: '' }],
        })} />
      )}

      <TouchableOpacity onPress={() => patch({ published: !space.published })}>
        <Text style={styles.link}>
          {space.published ? '☑ 公开空间，让别人发现我' : '☐ 公开空间，让别人发现我'}
        </Text>
      </TouchableOpacity>
      {!space.profile_public && (
        <View style={styles.card}>
          <Text style={styles.error}>当前账户设置为不公开个人资料，发布会被拦住。</Text>
          <Button title="允许公开个人资料" disabled={busy}
                  onPress={() => void allowPublicProfile()} />
        </View>
      )}

      <Button title={busy ? '正在保存…' : '保存空间'} disabled={busy} onPress={() => void save()} />
      {!!notice && <Text style={styles.muted}>{notice}</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}
      {space.published && me && (
        <TouchableOpacity onPress={() => onPreview(me.id)}>
          <Text style={styles.link}>看看我的门面 ↗</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 20, fontWeight: '700', color: '#2f6fed' },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 6, marginBottom: 10 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#dc2626' },
  link: { color: '#2f6fed', paddingVertical: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  chip: {
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14,
    backgroundColor: '#fff', borderWidth: 1, borderColor: '#e5e7eb', color: '#374151',
  },
  chipOn: { backgroundColor: '#2f6fed', borderColor: '#2f6fed', color: '#fff' },
});
