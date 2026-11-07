// AI-DEC-023 App 上的「再推一次」（320 号 spec）：没人报名的单，发单人一键再推，可选加价。
// 与 web 的 TaskReboostBox 同一份接口、同一句话；什么时候出现由共享 SDK 的 canReboostTask 判断。
import { apiErrorText, raiseToCents, taskReboostLine, type PlatformClient } from '@platform/core';
import { useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function TaskReboostBlock({ client, taskId, onDone }: { client: PlatformClient; taskId: number; onDone: () => void }) {
  const [yuan, setYuan] = useState('');
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  async function submit() {
    setError(''); setMsg('');
    const cents = raiseToCents(yuan);
    if (cents === null) { setError('加价写一个正数（元），最多两位小数；不加价就空着'); return; }
    try { setMsg(taskReboostLine(await client.reboostTask(taskId, cents))); setYuan(''); onDone(); }
    catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View accessibilityLabel="再推一次" style={styles.card}>
      <Text style={styles.row}>还没人报名？再推一次给附近有空、订阅了这个类目的人；加一点价更容易有人来。</Text>
      <TextInput style={styles.input} accessibilityLabel="加价（元）" placeholder="加价（元，可不填）"
                 keyboardType="decimal-pad" value={yuan} onChangeText={setYuan} />
      <TouchableOpacity style={styles.button} onPress={() => void submit()}>
        <Text style={styles.buttonText}>再推一次</Text>
      </TouchableOpacity>
      {!!msg && <Text style={styles.row}>{msg}</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  row: { fontSize: 14 },
  error: { color: '#b91c1c', fontSize: 13 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  button: { backgroundColor: '#275c52', borderRadius: 10, padding: 12, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600' },
});
