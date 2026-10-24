// SCN-166（297 号 spec）交付文件在 App 上：发布方先看预览，原图放款完毕前锁着。
// App 上暂时只看不传：上传原图、下载原图在网页版（下载要带登录态拿文件，App 端的保存到相册排进待办 SCN-168）。
import { type ContractDeliverable, type PlatformClient } from '@platform/core';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

export function DeliverablesList({ client, contractId, baseUrl = '' }: { client: PlatformClient; contractId: number; baseUrl?: string }) {
  const [rows, setRows] = useState<ContractDeliverable[]>([]);
  useEffect(() => { void client.contractDeliverables(contractId).then(setRows).catch(() => setRows([])); }, [client, contractId]);
  if (rows.length === 0) return null;
  const previews = rows.filter((d) => d.kind === 'preview' && d.url);
  const originals = rows.filter((d) => d.kind === 'original');
  const locked = originals.filter((d) => d.locked).length;
  return (
    <View style={s.card} accessibilityLabel="交付文件">
      <Text style={s.title}>交付文件</Text>
      <View style={s.row}>
        {previews.map((d) => <Image key={d.id} accessibilityLabel="预览" source={{ uri: `${baseUrl}${d.url}` }} style={s.img} />)}
      </View>
      {locked > 0 && <Text style={s.muted}>原图 {locked} 张：验收放款后可以下载</Text>}
      {originals.length - locked > 0 && <Text style={s.muted}>原图 {originals.length - locked} 张已可下载：请在网页版下载</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  img: { width: 72, height: 72, borderRadius: 8 },
});
