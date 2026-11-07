/**
 * RISK-010~014（399 号 spec，V426）举报入口与「我的举报」。
 *
 * 以前 Web 上普通用户找不到任何举报入口（只有后台的处置队列），App 也只能举报任务；
 * 《网络信息内容生态治理规定》第十六条要求平台设置便捷的投诉举报入口、及时处置并反馈结果。
 * 这里一个按钮四处用：任务、内容、用户（个人空间）、私信。
 */
import {
  MAX_REPORT_IMAGES, REPORT_CATEGORY_OPTIONS, apiErrorText, formatDateTime, reportStatusLine, reportSubmittedNote, reportTargetLabel,
  type MyReport, type ReportCategory, type ReportTarget,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { useApp } from './store';
import PhotoPicker from './PhotoPicker';

export function ReportButton({ targetType, targetId, label }: {
  targetType: ReportTarget; targetId: number; label?: string;
}) {
  const { client } = useApp();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ReportCategory>('other');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const what = reportTargetLabel(targetType);
  if (!open) {
    return <span>
      <button type="button" className="ghost" style={{ padding: '0 6px' }}
              aria-label={`举报这条${what}`} onClick={() => { setOpen(true); setNote(''); setError(''); }}>{label ?? '举报'}</button>
      {note && <span role="status" className="muted"> {note}</span>}
    </span>;
  }
  return (
    <div className="card" aria-label={`举报${what}`} style={{ marginTop: 6 }}>
      <label>哪一类问题
        <select aria-label="举报类型" value={category} onChange={(e) => setCategory(e.target.value as ReportCategory)}>
          {REPORT_CATEGORY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
      <textarea aria-label="举报说明" placeholder="说说哪里有问题（至少 2 个字，会进入人工审核）"
                value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      {/* RISK-017（404 号 spec）附截图，最多 3 张：聊天记录、页面截图让审核员不用只凭一句话判断 */}
      <span className="muted">截图（可选，最多 {MAX_REPORT_IMAGES} 张，截之前请遮住与举报无关的个人信息）</span>
      <PhotoPicker urls={images} onChange={setImages} max={MAX_REPORT_IMAGES} />
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="button" disabled={busy || reason.trim().length < 2} onClick={() => {
          setBusy(true); setError('');
          client.report(targetType, targetId, reason.trim(), category, images.length ? images : undefined)
            .then((r) => { setNote(reportSubmittedNote(r)); setOpen(false); setReason(''); setCategory('other'); setImages([]); })
            .catch((e) => setError(apiErrorText(e)))
            .finally(() => setBusy(false));
        }}>提交举报</button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>取消</button>
      </div>
    </div>
  );
}

export function MyReports() {
  const { client } = useApp();
  const [rows, setRows] = useState<MyReport[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    client.myReports()
      .then((r) => { if (live) setRows(Array.isArray(r?.items) ? r.items : []); })
      .catch((e) => { if (live) setError(apiErrorText(e)); });
    return () => { live = false; };
  }, [client]);
  return (
    <div className="card" aria-label="我的举报">
      <h3>我的举报</h3>
      <p className="muted">在任务、动态、个人空间和私信旁边点「举报」提交；处理完会通知你。</p>
      {error && <p className="error">{error}</p>}
      {rows && rows.length === 0 && <p className="muted">还没有举报过。</p>}
      {rows && rows.map((r) => (
        <div className="task-item" key={r.id} data-testid={`report-${r.id}`}>
          <div>
            <strong>{reportTargetLabel(r.target_type)} #{r.target_id}</strong> <span className="badge">{r.category_label}</span>
            <p className="muted">{r.reason}{Array.isArray(r.images) && r.images.length ? ` · 附图 ${r.images.length} 张` : ''} · {formatDateTime(r.created_at)}</p>
            <p>{reportStatusLine(r)}{r.resolved_at ? ` · ${formatDateTime(r.resolved_at)}` : ''}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
