// AI-DEC-001 App 上的「说一句话发单」（366 号 spec）：助手追问几句把需求问清，再用发布页模板预填（发不发由人定）。
// 与网页 /publish/clarify 同一份接口、同一句话。
import { apiErrorText, asList, clarifyProgressLine, clarifyTemplate, type ClarifyQuestion, type ClarifyResult,
  type PackTaskTemplateBrief, type PlatformClient } from '@platform/core';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

export function ClarifyScreen({ client, onUse }: { client: PlatformClient; onUse?: (t: PackTaskTemplateBrief) => void }) {
  const [text, setText] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ClarifyResult | null>(null);
  const [error, setError] = useState('');
  const ask = async (next: Record<string, string>) => {
    setError('');
    try {
      const r = await client.clarifyTask(text.trim(), next);
      // APP-091 响应畸形不白屏
      if (!r || typeof r !== 'object' || !r.draft) { setError('助手暂时没回上来，请稍后再试'); return; }
      setResult({ ...r, questions: asList<ClarifyQuestion>(r.questions) });
      setAnswers(next); setPending({});
    } catch (e) { setError(apiErrorText(e)); }
  };
  return (
    <View style={s.box} accessibilityLabel="说一句话发单">
      <Text style={s.muted}>说你要办什么事，我问几句把时间、地点、做到什么程度、怎么验收问清楚，再带到发布页。发不发、怎么改都由你定。</Text>
      <TextInput style={s.input} accessibilityLabel="你要办什么事" placeholder="比如：家里要打扫一下" value={text}
                 onChangeText={setText} maxLength={500} multiline />
      <Pressable accessibilityRole="button" disabled={text.trim().length < 2} onPress={() => void ask({})}>
        <Text style={text.trim().length < 2 ? s.muted : s.link}>{result ? '重新开始' : '开始'}</Text>
      </Pressable>
      {!!error && <Text style={s.error}>{error}</Text>}
      {result && (
        <View style={{ gap: 6 }}>
          <Text accessibilityRole="alert">{clarifyProgressLine(result)}</Text>
          {result.questions.map((q) => (
            <View key={q.key} style={{ gap: 4 }}>
              <Text>{q.ask}{q.required ? '' : '（选答）'}</Text>
              {asList<string>(q.options).length ? (
                <View style={s.row}>
                  {asList<string>(q.options).map((o) => (
                    <Pressable key={o} accessibilityRole="radio" accessibilityLabel={o} accessibilityState={{ selected: pending[q.key] === o }}
                               onPress={() => setPending({ ...pending, [q.key]: o })}>
                      <Text style={pending[q.key] === o ? s.chipOn : s.chip}>{o}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : (
                <TextInput style={s.input} accessibilityLabel={q.ask} value={pending[q.key] ?? ''} maxLength={200}
                           onChangeText={(v) => setPending({ ...pending, [q.key]: v })} />
              )}
            </View>
          ))}
          {!!result.questions.length && !result.blocked && (
            <Pressable accessibilityRole="button" onPress={() => void ask({ ...answers,
              ...Object.fromEntries(Object.entries(pending).filter(([, v]) => v.trim())) })}>
              <Text style={s.link}>回答</Text>
            </Pressable>
          )}
          {result.draft.on_behalf_hint && <Text style={s.muted}>说到了家里人：到发布页可以勾「替别人发」，对方的联系方式成交后才给接单的人。</Text>}
          {result.ready && (
            <>
              <Text accessibilityLabel="草稿">{result.draft.description}</Text>
              {onUse && <Pressable accessibilityRole="button" onPress={() => onUse(clarifyTemplate(result.draft))}>
                <Text style={s.link}>带到发布页</Text>
              </Pressable>}
            </>
          )}
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  box: { backgroundColor: '#fff', borderRadius: 12, padding: 12, gap: 8, borderWidth: 1, borderColor: '#e5e7eb' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { color: '#374151', borderWidth: 1, borderColor: '#d1d5db', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  chipOn: { color: '#fff', backgroundColor: '#2563eb', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  link: { color: '#2563eb', fontSize: 15, paddingVertical: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
});
