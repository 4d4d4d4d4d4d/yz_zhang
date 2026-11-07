// SRCH-001/003 全站搜索（V127，101 号 spec）。
//
// `search` / `searchSuggest` / `trendingTerms` 三个方法此前**三端零调用**——
// 72 号台账自己写着「找不到东西的平台等于没有内容」。
//
// 接之前先修了服务端两处（见 101 号 spec）：
// - 联想与热词原样公开**任何人敲过的原始搜索串**，一次就够。
//   有人搜过「张三 13800001234」，任何人在框里打「张」都能看到它。
// - 用户搜索不看隐私设置：设了「资料不公开」的人、已注销的人照样被搜出来。
// 所以这一页显示的热词，是**至少 3 个不同的人搜过、且过了内容审核**的词。
import { apiErrorText, fmtYuan, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Results = Awaited<ReturnType<PlatformClient['search']>>;

export function SearchScreen({ client, onOpenSpace, onOpenTask }: {
  client: PlatformClient;
  onOpenSpace: (userId: number) => void;
  onOpenTask: (taskId: number) => void;
}) {
  const [q, setQ] = useState('');
  const [suggest, setSuggest] = useState<string[]>([]);
  const [trending, setTrending] = useState<Array<{ term: string; count: number }>>([]);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // 联想是边打边发的：慢的那个回来时，框里可能已经是别的字了
  const seq = useRef(0);

  useEffect(() => {
    void client.trendingTerms(8).then(setTrending).catch(() => setTrending([]));
  }, [client]);

  useEffect(() => {
    const term = q.trim();
    if (!term) { setSuggest([]); return; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      void client.searchSuggest(term)
        .then((s) => { if (mine === seq.current) setSuggest(s.filter((x) => x !== term)); })
        .catch(() => { if (mine === seq.current) setSuggest([]); });
    }, 250);
    return () => clearTimeout(t);
  }, [client, q]);

  const run = useCallback(async (term: string) => {
    const t = term.trim();
    if (!t) return;
    setQ(t); setSuggest([]); setBusy(true); setError('');
    try {
      setResults(await client.search(t));
    } catch (e) {
      setError(apiErrorText(e));
      setResults(null);
    } finally {
      setBusy(false);
    }
  }, [client]);

  const empty = results
    && !results.tasks.length && !results.users.length
    && !results.contents.length && !results.circles.length;

  return (
    <View style={{ gap: 12 }}>
      <TextInput style={styles.input} value={q} onChangeText={setQ}
                 placeholder="搜任务、人、内容、圈层…" returnKeyType="search"
                 onSubmitEditing={() => void run(q)} />
      {suggest.length > 0 && (
        <View style={styles.card}>
          {suggest.map((s) => (
            <TouchableOpacity key={s} onPress={() => void run(s)}>
              <Text style={styles.row}>{s}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {!results && !busy && trending.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.title}>大家在搜</Text>
          <View style={styles.chips}>
            {trending.map((t) => (
              <TouchableOpacity key={t.term} onPress={() => void run(t.term)}>
                <Text style={styles.chip}>{t.term}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {busy && <Text style={styles.muted}>正在搜…</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}
      {empty && <Text style={styles.muted}>没有找到相关结果，换个说法试试。</Text>}

      {results && results.tasks.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.title}>任务</Text>
          {results.tasks.map((t) => (
            <TouchableOpacity key={t.id} onPress={() => onOpenTask(t.id)}>
              <Text style={styles.row}>{t.title}</Text>
              <Text style={styles.muted}>{t.category} · {t.city || '线上'} · {fmtYuan(t.budget_cents)}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {results && results.users.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.title}>人</Text>
          {results.users.map((u) => (
            <TouchableOpacity key={u.id} onPress={() => onOpenSpace(u.id)}>
              <Text style={styles.row}>{u.nickname}</Text>
              <Text style={styles.muted}>
                {u.skills.slice(0, 3).join(' · ') || '未填写技能'} · 信用 {u.credit_score}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {results && results.contents.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.title}>内容</Text>
          {results.contents.map((c) => (
            <View key={c.id}>
              <Text style={styles.row}>{c.title}</Text>
              <Text style={styles.muted} numberOfLines={2}>{c.body}</Text>
            </View>
          ))}
        </View>
      )}
      {results && results.circles.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.title}>圈层</Text>
          {results.circles.map((c) => (
            <View key={c.id}>
              <Text style={styles.row}>{c.name}</Text>
              <Text style={styles.muted}>{c.member_count} 人</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 16, gap: 8, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  row: { fontSize: 15 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { backgroundColor: '#f1f5f2', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6 },
});
