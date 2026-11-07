// OUT-052（444 号 spec）App 发单页「按结果计价」：预算是基础报酬，达标另外加付（加付部分也先托管）。
// 请求体与网页同一份（SDK outcomePayload）；规则都在服务端，没填完的当场说清。
import { outcomePayload, type OutcomePayload, type OutcomeTierDraft } from '@platform/core';
import { StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';

export type OutcomeDraft = { on: boolean; keywords: string; bonusYuan: string; tiers: OutcomeTierDraft[] };
export const EMPTY_OUTCOME: OutcomeDraft = { on: false, keywords: '', bonusYuan: '', tiers: [] };

/** 开着时返回要并进请求体的字段（含 pricing）或 { error }；关着返回 {}。 */
export function outcomeFields(d: OutcomeDraft): (OutcomePayload & { pricing: 'outcome' }) | { error: string } | Record<string, never> {
  if (!d.on) return {};
  const p = outcomePayload(d);
  return 'error' in p ? p : { pricing: 'outcome', ...p };
}

export function OutcomeFields({ value, onChange }: { value: OutcomeDraft; onChange: (v: OutcomeDraft) => void }) {
  const setTier = (i: number, patch: Partial<OutcomeTierDraft>) =>
    onChange({ ...value, tiers: value.tiers.map((t, j) => (j === i ? { ...t, ...patch } : t)) });
  return (
    <View style={s.box}>
      <View style={s.row}>
        <Text style={{ flex: 1 }}>按结果计价（达标加付）</Text>
        <Switch accessibilityLabel="按结果计价" value={value.on} onValueChange={(on) => onChange({ ...value, on })} />
      </View>
      {value.on && (
        <>
          <Text style={s.muted}>预算是基础报酬；交付说明里写明下面的关键词就算达标，加付部分发布时一起托管。</Text>
          <TextInput accessibilityLabel="达标关键词" style={s.input} placeholder="关键词，用逗号隔开（如：已自测，已部署）"
                     value={value.keywords} onChangeText={(keywords) => onChange({ ...value, keywords })} />
          <TextInput accessibilityLabel="全部达标加付" style={s.input} keyboardType="numeric" editable={!value.tiers.length}
                     placeholder="全部达标加付多少元" value={value.bonusYuan} onChangeText={(bonusYuan) => onChange({ ...value, bonusYuan })} />
          <Text style={s.muted}>也可以分档：通过的条数越多加付越多，取达到的最高一档、不累加。</Text>
          {value.tiers.map((t, i) => (
            <View key={i} style={s.row}>
              <TextInput accessibilityLabel={`第${i + 1}档通过几条`} style={[s.input, { flex: 1 }]} keyboardType="numeric"
                         placeholder="通过几条" value={t.min_passed} onChangeText={(min_passed) => setTier(i, { min_passed })} />
              <TextInput accessibilityLabel={`第${i + 1}档加付`} style={[s.input, { flex: 1 }]} keyboardType="numeric"
                         placeholder="加付多少元" value={t.yuan} onChangeText={(yuan) => setTier(i, { yuan })} />
              <TouchableOpacity onPress={() => onChange({ ...value, tiers: value.tiers.filter((_, j) => j !== i) })}>
                <Text style={s.link}>删去</Text>
              </TouchableOpacity>
            </View>
          ))}
          {value.tiers.length < 5 && (
            <TouchableOpacity onPress={() => onChange({ ...value, tiers: [...value.tiers, { min_passed: '', yuan: '' }] })}>
              <Text style={s.link}>＋加一档</Text>
            </TouchableOpacity>
          )}
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 6, paddingVertical: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  muted: { color: '#6b7280', fontSize: 12 },
  link: { color: '#275c52', fontWeight: '600' },
});
