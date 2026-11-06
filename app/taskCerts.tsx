// SCN-294b（407 号 spec，V434）发单人按这一单加选资质（App）。
//
// 类目列出可加的资质（例如展台搭建：2 米以上作业要高处作业证、接电要电工证；无人机航拍：小型机要操控员执照），
// 发单人这一单需要就勾上，报名的人要都有审核通过的证件。不需要就别勾：多要一张证，能接单的人就少一批。
import { ADD_CERT_HINT, addableCerts, addCertPatch, apiErrorText, optionalCerts, taskCertsLine, type Category, type PlatformClient } from '@platform/core';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export function TaskCertsPicker({ client, category, value, onChange }: {
  client: PlatformClient; category: string; value: string[]; onChange: (v: string[]) => void;
}) {
  const [offered, setOffered] = useState<string[]>([]);
  useEffect(() => {
    let live = true;
    client.categories()
      .then((cs: Category[]) => {
        if (!live) return;
        const opts = optionalCerts(Array.isArray(cs) ? cs.find((c) => c.name === category) : null);
        setOffered(opts);
        onChange(value.filter((x) => opts.includes(x)));     // 换了类目：只留新类目也能加的
      })
      .catch(() => { if (live) setOffered([]); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, category]);
  if (!offered.length) return null;
  return (
    <View accessibilityLabel="这一单另外要的资质" style={{ gap: 4 }}>
      <Text style={s.muted}>这一单另外要的资质（报名的人要有审核通过的证件；不需要就别勾）</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {offered.map((c) => {
          const on = value.includes(c);
          return (
            <TouchableOpacity key={c} accessibilityLabel={`加选资质：${c}`} accessibilityState={{ selected: on }}
                              onPress={() => onChange(on ? value.filter((x) => x !== c) : [...value, c])}>
              <Text style={[s.chip, on && s.chipOn]}>{on ? '✓ ' : ''}{c}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

/** 任务详情里的一句：发单人为这一单加选了哪些资质 */
export function TaskCertsNote({ task }: { task: { task_certs?: unknown } }) {
  const line = taskCertsLine(task);
  return line ? <Text style={s.muted} accessibilityLabel="这一单另外要的资质">⚠️ {line}</Text> : null;
}

const s = StyleSheet.create({
  muted: { color: '#666' },
  chip: { borderWidth: 1, borderColor: '#ccc', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  chipOn: { borderColor: '#1565c0', color: '#1565c0' },
});

/** SCN-294f（426 号 spec）发布后加上加选资质（发单人、招募中）。已报名的人里有没证的，服务端拒，理由原样显示。 */
export function TaskCertsAdd({ client, task, onChanged }: {
  client: PlatformClient; task: { id: number; category: string; task_certs?: unknown }; onChanged: () => void | Promise<void>;
}) {
  const [offered, setOffered] = useState<string[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    Promise.resolve().then(() => client.categories())
      .then((cs: Category[]) => { if (live) setOffered(addableCerts(task, Array.isArray(cs) ? cs.find((c) => c.name === task.category) : null)); })
      .catch(() => { if (live) setOffered([]); });
    return () => { live = false; };
  }, [client, task]);
  if (!offered.length) return null;
  return (
    <View accessibilityLabel="加上这一单另外要的资质" style={{ gap: 4 }}>
      <Text style={s.muted}>这一单还可以另外要：{ADD_CERT_HINT}</Text>
      {!!error && <Text style={{ color: '#b91c1c' }}>{error}</Text>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {offered.map((c) => (
          <TouchableOpacity key={c} style={s.chip} onPress={async () => {
            setError('');
            try {
              await client.editTask(task.id, addCertPatch(task, c));
              await onChanged();
            } catch (e) {
              setError(apiErrorText(e));
            }
          }}>
            <Text>加上「{c}」</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}
