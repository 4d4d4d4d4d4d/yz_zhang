// SCN-123 发单后改服务对象（197 号 spec）：替别人发的单，换了人、换了联系方式不用取消重发；都要再问过本人。
import { apiErrorText, type PlatformClient, type Task } from '@platform/core';
import { useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function canChangeRecipient(task: Pick<Task, 'on_behalf' | 'status' | 'creator_id'>, meId: number | null | undefined): boolean {
  return !!task.on_behalf && meId === task.creator_id && !['completed', 'cancelled', 'disputed'].includes(task.status);
}

export function RecipientEditorBlock({ client, task, onChanged }: { client: PlatformClient; task: Task; onChanged: () => void | Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(task.recipient_label ?? '');
  const [phone, setPhone] = useState(task.onsite_contact ?? '');
  const [consented, setConsented] = useState(false);
  const [msg, setMsg] = useState('');
  if (!open) {
    return (
      <View>
        <TouchableOpacity onPress={() => { setOpen(true); setMsg(''); }}><Text style={styles.link}>改服务对象</Text></TouchableOpacity>
        {!!msg && <Text style={styles.muted}>{msg}</Text>}
      </View>
    );
  }
  async function save() {
    setMsg('');
    try {
      await client.changeRecipient(task.id, { recipient_label: name, onsite_contact: phone, recipient_consented: consented });
      setOpen(false); setConsented(false); setMsg('已改好，接单的人会收到通知');
      await onChanged();
    } catch (e) { setMsg(apiErrorText(e)); }
  }
  return (
    <View style={styles.card} accessibilityLabel="改服务对象">
      <TextInput style={styles.input} accessibilityLabel="服务对象怎么称呼" value={name} onChangeText={setName} />
      <TextInput style={styles.input} accessibilityLabel="到场联系方式" value={phone} onChangeText={setPhone} />
      <TouchableOpacity accessibilityRole="checkbox" accessibilityLabel="已经问过本人" accessibilityState={{ checked: consented }}
                        onPress={() => setConsented((c) => !c)}>
        <Text style={styles.row}>{consented ? '☑ ' : '☐ '}已经问过本人（换了人或改了联系方式，要再问一次）</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => void save()}><Text style={styles.link}>保存</Text></TouchableOpacity>
      <TouchableOpacity onPress={() => setOpen(false)}><Text style={styles.muted}>取消</Text></TouchableOpacity>
      {!!msg && <Text style={styles.muted}>{msg}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: '#e5e7eb' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  row: { fontSize: 14, color: '#1f2937' },
  link: { color: '#2563eb', fontSize: 14, paddingVertical: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
});
