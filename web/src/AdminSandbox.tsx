import { apiErrorText, type SandboxModelAdminRow, type SandboxModelInput } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** SBX-106 端侧模型目录运营（128 号 spec）：登记 → 另一位管理员上架（必须有 sha256、https 地址、大小、许可证、最低内存）→ 下架。 */
const STATUS: Record<SandboxModelAdminRow['status'], string> = { draft: '草稿', published: '已上架', retired: '已下架' };
const EMPTY = { key: '', name: '', params_b: '', quant: 'Q4_K_M', size_mb: '', sha256: '', url: '', license: '', min_ram_gb: '', skills: 'summarize todos checklist' };

export function SandboxModelsAdmin() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<SandboxModelAdminRow[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [editing, setEditing] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { const r = await client.adminSandboxModels(); setRows(Array.isArray(r) ? r : []); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  function input(): SandboxModelInput {
    return {
      key: form.key.trim(), name: form.name.trim(), params_b: Number(form.params_b) || 0, quant: form.quant.trim(),
      size_mb: Number(form.size_mb) || 0, sha256: form.sha256.trim(), url: form.url.trim(), license: form.license.trim(),
      min_ram_gb: Number(form.min_ram_gb) || 0, skills: form.skills.split(/[\s,，]+/).filter(Boolean),
    };
  }
  function edit(r: SandboxModelAdminRow) {
    setEditing(r.id);
    setForm({ key: r.key, name: r.name, params_b: String(r.params_b), quant: r.quant, size_mb: String(r.size_mb), sha256: r.sha256,
      url: r.url, license: r.license, min_ram_gb: String(r.min_ram_gb), skills: r.skills.join(' ') });
  }
  const field = (k: keyof typeof EMPTY, label: string) => (
    <input aria-label={label} placeholder={label} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
  );

  return (
    <div className="card" aria-label="端侧模型目录">
      <h3>端侧模型目录（隐私沙箱）</h3>
      <p className="muted">手机直接从登记的地址下载、按 sha256 校验；登记的人不能自己上架。</p>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <div className="row">
        {field('key', '模型标识')}{field('name', '名称')}{field('params_b', '参数量（十亿）')}{field('quant', '量化')}
        {field('size_mb', '大小（MB）')}{field('min_ram_gb', '最低内存（GB）')}{field('license', '许可证')}
      </div>
      <div className="row">
        <input className="grow" aria-label="下载地址" placeholder="https 下载地址" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        <input className="grow" aria-label="sha256" placeholder="sha256（64 位十六进制）" value={form.sha256} onChange={(e) => setForm({ ...form, sha256: e.target.value })} />
        {field('skills', '本机技能（空格分开）')}
        {editing === null
          ? <button disabled={!form.key || !form.name} onClick={() => void act(async () => { await client.createSandboxModel(input()); setForm({ ...EMPTY }); }, '已登记为草稿：请另一位管理员核对后上架')}>登记</button>
          : <button onClick={() => void act(async () => { await client.updateSandboxModel(editing, input()); setEditing(null); setForm({ ...EMPTY }); }, '已保存')}>保存修改</button>}
      </div>
      <table style={{ marginTop: 8 }}>
        <thead><tr><th>模型</th><th>规格</th><th>校验</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}<div className="muted">{r.key}</div></td>
              <td>{r.params_b}B · {r.quant} · {r.size_mb} MB · ≥{r.min_ram_gb} GB</td>
              <td>{r.sha256 ? `${r.sha256.slice(0, 10)}…` : '缺 sha256'}</td>
              <td>{STATUS[r.status]}{r.retired_reason ? `（${r.retired_reason}）` : ''}</td>
              <td>
                {r.status === 'draft' && <button className="text-link" onClick={() => edit(r)}>改</button>}
                {r.status === 'draft' && r.created_by !== me?.id
                  && <button className="text-link" onClick={() => void act(() => client.publishSandboxModel(r.id), `已上架：${r.name}`)}>上架</button>}
                {r.status === 'published' && <button className="text-link" onClick={() => {
                  const reason = window.prompt('下架原因（会留在审计里）');
                  if (reason) void act(() => client.retireSandboxModel(r.id, reason), `已下架：${r.name}`);
                }}>下架</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
