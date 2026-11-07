// SCN-219 App 上的发单复核（336 号 spec）：发布被拦下时写一句说明申请人工复核；发布页下面列出我申请过的。
// 与 web 的 ErrandReviewRequest 同一份接口、同一句话。
import { apiErrorText, ERRAND_REVIEW_MIN_EXPLANATION, errandReviewLine, type ErrandReviewItem, type PlatformClient } from '@platform/core';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

export function ErrandReviewRequest({ client, title, description, onSent }: {
  client: PlatformClient; title: string; description: string; onSent?: (r: ErrandReviewItem) => void;
}) {
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState('');
  const [done, setDone] = useState<ErrandReviewItem | null>(null);
  const [error, setError] = useState('');
  if (done) return <Text style={s.muted} accessibilityRole="text">已申请复核：{errandReviewLine(done)}</Text>;
  if (!open) {
    return <Pressable accessibilityRole="button" onPress={() => setOpen(true)}><Text style={s.link}>觉得拦错了？申请人工复核</Text></Pressable>;
  }
  const ready = explanation.trim().length >= ERRAND_REVIEW_MIN_EXPLANATION;
  return (
    <View accessibilityLabel="申请人工复核" style={s.box}>
      <Text style={s.muted}>运营会看你的标题、说明和下面这句话。通过后这段文字可以发一单；改了文字要重新判断。</Text>
      <TextInput style={s.input} accessibilityLabel="复核说明" placeholder="你要办的到底是什么事、为什么不是被拦的那一类"
                 value={explanation} onChangeText={setExplanation} maxLength={300} multiline />
      <Pressable accessibilityRole="button" accessibilityState={{ disabled: !ready }} disabled={!ready} onPress={async () => {
        setError('');
        try {
          const r = await client.requestErrandReview(title, description, explanation.trim());
          setDone(r);
          onSent?.(r);
        } catch (e) { setError(apiErrorText(e)); }
      }}><Text style={ready ? s.link : s.muted}>提交复核</Text></Pressable>
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

/** 我申请过的复核：通过了的提示原样再发，维持的给出理由。没有就不显示。 */
export function MyErrandReviews({ client, refresh = 0 }: { client: PlatformClient; refresh?: number }) {
  const [rows, setRows] = useState<ErrandReviewItem[]>([]);
  useEffect(() => {
    void client.myErrandReviews().then((v) => setRows(Array.isArray(v) ? v.slice(0, 5) : [])).catch(() => setRows([]));
  }, [client, refresh]);
  if (rows.length === 0) return null;
  return (
    <View accessibilityLabel="我的发单复核" style={s.box}>
      <Text style={s.head}>我的发单复核</Text>
      {rows.map((r) => <Text key={r.id} style={s.muted}>{errandReviewLine(r)}</Text>)}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 6, paddingVertical: 6 },
  head: { fontWeight: '600' },
  muted: { color: '#666' },
  link: { color: '#2563eb' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 6, padding: 8, minHeight: 60 },
});
