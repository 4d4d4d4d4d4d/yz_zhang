// SCN-166（297 号 spec）交付文件托管在平台：执行方传预览图（自己加水印或缩小）和原图；
// 发布方马上能看预览，原图在合约放款完毕后才能下载——「先交片后不付」「付了不交片」两头都堵上。
import { apiErrorText, type ContractDeliverable } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

const MAX_BYTES = 2 * 1024 * 1024;

/** 原图不压缩：读成 base64 原样上传（服务端上限 2MB） */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',')[1] ?? '');
    r.onerror = () => reject(new Error('读取文件失败'));
    r.readAsDataURL(file);
  });
}

export default function DeliverablesBlock({ contractId, isExecutor, live }: { contractId: number; isExecutor: boolean; live: boolean }) {
  const { client } = useApp();
  const [rows, setRows] = useState<ContractDeliverable[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setRows(await client.contractDeliverables(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);

  async function upload(kind: ContractDeliverable['kind'], files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setError('');
    if (file.size > MAX_BYTES) { setError('单个文件最大 2MB：请压缩后再传'); return; }
    setBusy(true);
    try {
      const r = await client.uploadImage(file.type, await fileToBase64(file));
      await client.addDeliverable(contractId, r.ref, kind);
      await load();
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }
  async function download(d: ContractDeliverable) {
    setError('');
    try {
      const url = URL.createObjectURL(await client.downloadDeliverable(contractId, d.id));
      const a = document.createElement('a'); a.href = url; a.download = `原图-${d.id}`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(apiErrorText(e)); }
  }

  const previews = rows.filter((d) => d.kind === 'preview');
  const originals = rows.filter((d) => d.kind === 'original');
  const locked = originals.filter((d) => d.locked);
  if (rows.length === 0 && !(isExecutor && live)) return null;
  return (
    <div aria-label="交付文件" style={{ marginTop: 10 }}>
      <h4>交付文件</h4>
      {previews.length > 0 && (
        <div className="row" style={{ gap: 6 }}>
          {previews.map((d) => d.url && <img key={d.id} src={d.url} alt="预览" width={96} height={96} style={{ objectFit: 'cover', borderRadius: 8 }} />)}
        </div>
      )}
      {locked.length > 0 && <p className="muted" data-testid="originals-locked">原图 {locked.length} 张：验收放款后可以下载</p>}
      {originals.filter((d) => !d.locked).map((d) => (
        <button key={d.id} className="ghost" onClick={() => void download(d)}>下载原图 #{d.id}</button>
      ))}
      {isExecutor && live && (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <label className="muted">上传预览图（建议自己加水印或缩小）
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-label="上传预览图" disabled={busy}
                   onChange={(e) => void upload('preview', e.target.files)} />
          </label>
          <label className="muted">上传原图（发布方放款后才能下载）
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-label="上传原图" disabled={busy}
                   onChange={(e) => void upload('original', e.target.files)} />
          </label>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
