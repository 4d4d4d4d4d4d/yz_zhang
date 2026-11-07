// MOB-021 拍照/相册取图：客户端先压缩再上传。
//
// 压缩不是优化，是必需：手机直出照片常有 3~8MB，既超过服务端 2MB 上限，
// 也会让弱网下的执行者传半天传不上去——而交付凭证传不上去等于没有证据。
import { useRef, useState } from 'react';
import { useApp } from './store';

const MAX_EDGE = 1280; // 长边上限：凭证类照片够看清即可
const QUALITY = 0.8;

export async function compressToBase64(file: File): Promise<{ contentType: string; data: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('当前浏览器不支持图片压缩');
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', QUALITY);
  return { contentType: 'image/jpeg', data: dataUrl.split(',')[1] ?? '' };
}

interface Props {
  urls: string[];
  onChange: (urls: string[]) => void;
  max?: number;
}

export default function PhotoPicker({ urls, onChange, max = 9 }: Props) {
  const { client } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function pick(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError('');
    try {
      const room = max - urls.length;
      const next: string[] = [];
      for (const file of Array.from(files).slice(0, room)) {
        const { contentType, data } = await compressToBase64(file);
        const r = await client.uploadImage(contentType, data);
        next.push(r.url);
      }
      onChange([...urls, ...next]);
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传失败');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <div className="row" style={{ gap: 8 }}>
      {urls.map((u) => (
        <span key={u} className="row" style={{ gap: 4 }}>
          <img src={u} alt="凭证" width={56} height={56}
               style={{ objectFit: 'cover', borderRadius: 8 }} />
          <button className="ghost" aria-label="移除图片"
                  onClick={() => onChange(urls.filter((x) => x !== u))}>×</button>
        </span>
      ))}
      {urls.length < max && (
        <>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            capture="environment"   /* 手机上直接唤起后置摄像头 */
            multiple
            style={{ display: 'none' }}
            onChange={(e) => void pick(e.target.files)}
            data-testid="photo-input"
          />
          <button className="ghost" disabled={busy} onClick={() => inputRef.current?.click()}>
            {busy ? '上传中…' : '📷 加图片'}
          </button>
        </>
      )}
      {error && <span className="error">{error}</span>}
    </div>
  );
}
