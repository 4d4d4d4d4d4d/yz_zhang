// SCN-156（278 号 spec）作品展示授权：已完成的单，发单人可以允许接单人把这一单（前后对比照、成品）放进作品集；随时撤回。
import { apiErrorText, type PlatformClient, type Task } from '@platform/core';
import { useState } from 'react';
import { Text, TouchableOpacity, View } from 'react-native';

export function canGrantShowcase(task: Pick<Task, 'status' | 'creator_id' | 'executor_id'>, meId: number | null | undefined): boolean {
  return task.status === 'completed' && task.executor_id !== null && meId === task.creator_id;
}

export function ShowcaseConsentBlock({ client, task, onChanged }: { client: PlatformClient; task: Task; onChanged: () => void | Promise<void> }) {
  const [msg, setMsg] = useState('');
  const granted = !!task.showcase_consent_at;
  async function toggle() {
    setMsg('');
    try {
      if (granted) await client.withdrawShowcaseConsent(task.id);
      else await client.grantShowcaseConsent(task.id);
      setMsg(granted ? '已撤回：对方空间里关联这一单的作品不再公开' : '已允许：对方可以在空间里把这一单当作品展示，你随时可以撤回');
      await onChanged();
    } catch (e) { setMsg(apiErrorText(e)); }
  }
  return (
    <View accessibilityLabel="作品展示授权">
      <Text>{granted ? '你已允许接单人把这一单放进作品集' : '接单人想把这一单（前后对比照、成品）放进作品集，要你同意'}</Text>
      <TouchableOpacity onPress={() => void toggle()}><Text style={{ color: '#2563eb' }}>{granted ? '撤回展示授权' : '允许展示这一单'}</Text></TouchableOpacity>
      {!!msg && <Text>{msg}</Text>}
    </View>
  );
}
