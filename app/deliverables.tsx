// SCN-166（297 号 spec）交付文件在 App 上：发布方先看预览，原图放款完毕前锁着。
// SCN-168（300 号 spec）执行方在 App 上也能传：从相册选图，原图按原质量上传（服务端上限 2MB，本地先拦）。
// 放款后的原图保存到相册要新依赖（相册写入），本批没有接，记作 SCN-174；仍提示到网页版下载。
// SC-017（304 号 spec）多于一期时执行方可以选「挂到哪一期」，那一期放款后原图就解锁。
import {
  apiErrorText, deliverableLockedText, deliverableStageTag, type ContractDeliverable, type Milestone, type PlatformClient,
} from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useState } from 'react';
import { Button, Image, Pressable, StyleSheet, Text, View } from 'react-native';

const MAX_BYTES = 2 * 1024 * 1024;

export function DeliverablesList({ client, contractId, baseUrl = '', isExecutor = false, live = false, stages }: {
  client: PlatformClient; contractId: number; baseUrl?: string; isExecutor?: boolean; live?: boolean;
  stages?: Pick<Milestone, 'idx' | 'title' | 'status'>[];
}) {
  const [rows, setRows] = useState<ContractDeliverable[]>([]);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setRows(await client.contractDeliverables(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);

  async function pick(kind: ContractDeliverable['kind']) {
    setError('');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm.status !== 'granted') { setError('没有相册权限，请在系统设置里允许后重试'); return; }
    // 原图按原质量传，预览图压一压
    const r = await ImagePicker.launchImageLibraryAsync({ quality: kind === 'original' ? 1 : 0.6, base64: true });
    if (r.canceled) return;
    const asset = r.assets?.[0];
    if (!asset?.base64) { setError('读不到图片数据，请换一张'); return; }
    if ((asset.base64.length / 4) * 3 > MAX_BYTES) { setError('单个文件最大 2MB：请压缩后再传'); return; }
    setBusy(true);
    try {
      const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
      await client.addDeliverable(contractId, up.ref, kind, stage || undefined);
      await load();
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  const canUpload = isExecutor && live;
  if (rows.length === 0 && !canUpload) return null;
  const previews = rows.filter((d) => d.kind === 'preview' && d.url);
  const originals = rows.filter((d) => d.kind === 'original');
  const lockedRows = originals.filter((d) => d.locked);
  const locked = lockedRows.length;
  const openStages = (stages ?? []).filter((m) => m.status !== 'released');
  return (
    <View style={s.card} accessibilityLabel="交付文件">
      <Text style={s.title}>交付文件</Text>
      <View style={s.row}>
        {previews.map((d) => <Image key={d.id} accessibilityLabel={`预览${deliverableStageTag(d)}`} source={{ uri: `${baseUrl}${d.url}` }} style={s.img} />)}
      </View>
      {locked > 0 && <Text style={s.muted}>{deliverableLockedText(lockedRows)}</Text>}
      {originals.length - locked > 0 && <Text style={s.muted}>原图 {originals.length - locked} 张已可下载：请在网页版下载</Text>}
      {canUpload && (stages?.length ?? 0) > 1 && openStages.length > 0 && (
        <View style={s.row} accessibilityLabel="挂到哪一期">
          {[{ idx: 0, label: '整份合约' }, ...openStages.map((m) => ({ idx: m.idx, label: `第 ${m.idx} 期 ${m.title}` }))].map((o) => (
            <Pressable key={o.idx} onPress={() => setStage(o.idx)} accessibilityRole="radio"
                       accessibilityState={{ selected: stage === o.idx }} style={[s.chip, stage === o.idx && s.chipOn]}>
              <Text>{o.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
      {canUpload && (
        <View style={s.row}>
          <Button title="上传预览图" disabled={busy} onPress={() => void pick('preview')} />
          <Button title="上传原图" disabled={busy} onPress={() => void pick('original')} />
        </View>
      )}
      {canUpload && <Text style={s.muted}>预览图建议自己加水印或缩小；原图在发布方放款后才能下载。</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#b91c1c' },
  img: { width: 72, height: 72, borderRadius: 8 },
  chip: { borderWidth: 1, borderColor: '#ddd', borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  chipOn: { borderColor: '#2563eb', backgroundColor: '#eff6ff' },
});
