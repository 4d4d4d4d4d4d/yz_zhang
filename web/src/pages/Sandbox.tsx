import {
  LOCAL_SKILL_NAMES, REDACT_NAMES, apiErrorText, askLocal, redact, runLocal,
  type LocalResult, type LocalSkill, type SandboxModelList, type SandboxState,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { useApp } from '../store';
import { loadLocalNotes, readSandbox, saveLocalNotes, writeSandbox, type LocalNote } from '../sandboxLocal';

/** SBX-100 隐私沙箱（128 号 spec）。
 *
 * 开着时：助手的活（摘要、拆清单、抽待办、改写、起草回复）在这台设备上本机做，原文不发到云端；
 * 把原文交给云端 AI 的请求在发出之前就被拦下。本机笔记只存在这个浏览器里。
 * 要放进云端知识库，先脱敏、给你看遮了什么、你确认了才发。手机 App 上可以下载端侧量化小模型；浏览器里用本机规则。
 */
const SKILLS: LocalSkill[] = ['summarize', 'checklist', 'todos', 'rewrite', 'reply'];

export default function Sandbox() {
  const { client } = useApp();
  const [state, setState] = useState<SandboxState | null>(null);
  const [local, setLocal] = useState(readSandbox());
  const [notes, setNotes] = useState<LocalNote[]>(loadLocalNotes);
  const [text, setText] = useState('');
  const [instruction, setInstruction] = useState('');
  const [result, setResult] = useState<LocalResult | null>(null);
  const [refused, setRefused] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [catalog, setCatalog] = useState<SandboxModelList | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    client.mySandbox().then((s) => {
      setState(s);
      // 服务端记着开着而这台设备没开：以开着为准（更保守）
      if (s.enabled && !readSandbox()) { writeSandbox(true); setLocal(true); }
    }).catch((e) => setError(apiErrorText(e)));
    client.sandboxModels().then(setCatalog).catch(() => setCatalog(null));
  }, [client]);

  async function toggle() {
    setError(''); setNotice('');
    const next = !local;
    // 打开：先在本机生效（拦截立刻起作用），再告诉服务端；关闭：先告诉服务端，成功了再在本机关
    if (next) { writeSandbox(true); setLocal(true); }
    try {
      setState(await client.setSandbox(next));
      if (!next) { writeSandbox(false); setLocal(false); }
      setNotice(next ? '隐私沙箱已打开：助手的活在本机做' : '隐私沙箱已关闭：可以用云端助手了');
    } catch (e) { setError(apiErrorText(e)); }
  }

  function saveNote() {
    if (!text.trim()) return;
    const n: LocalNote = { id: String(Date.now()), text: text.trim(), updated_at: Date.now() };
    const next = [n, ...notes].slice(0, 200);
    setNotes(next); saveLocalNotes(next); setNotice('已存在本机（这个浏览器里）');
  }
  function removeNote(id: string) {
    const next = notes.filter((n) => n.id !== id);
    setNotes(next); saveLocalNotes(next);
  }

  async function run(skill?: LocalSkill) {
    setRefused(''); setConfirm(false);
    if (skill) { setResult(await runLocal(skill, text)); return; }
    const r = await askLocal(instruction, text);
    if ('refused' in r) { setResult(null); setRefused(r.refused); } else setResult(r);
  }

  const outgoing = result ? redact(result.output) : null;
  async function sync() {
    if (!outgoing || !confirm) return;
    setError('');
    try {
      await client.createNote({ body: outgoing.text, title: `本机助手：${LOCAL_SKILL_NAMES[result!.skill]}`, tags: ['本机助手'] });
      setNotice('脱敏后的结果已放进你的知识库'); setConfirm(false);
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>隐私沙箱</h2>
        <p className="muted">{state?.note ?? '开着时，助手的活在本机做，原文不发到云端。'}</p>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <div className="card row" aria-label="沙箱开关">
        <strong className="grow">{local ? `● 隐私沙箱开着：${state?.blocked_endpoints ?? ''} 类云端助手接口被拦下` : '隐私沙箱关着'}</strong>
        <button className={local ? 'ghost' : ''} onClick={() => void toggle()}>{local ? '关闭沙箱' : '打开沙箱'}</button>
      </div>

      <div className="card" aria-label="本机助手">
        <h4>本机助手</h4>
        <textarea aria-label="本机内容" rows={6} placeholder="贴一段纪要、消息或要做的事（只在这台设备上）" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row">
          {SKILLS.map((k) => <button key={k} className="ghost" disabled={!text.trim()} onClick={() => void run(k)}>{LOCAL_SKILL_NAMES[k]}</button>)}
          <button className="ghost" disabled={!text.trim()} onClick={saveNote}>存在本机</button>
        </div>
        <div className="row">
          <input className="grow" aria-label="一句话指令" placeholder="或者直接说：帮我抽出待办 / 拆成步骤 / 回复一下" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          <button disabled={!instruction.trim() || !text.trim()} onClick={() => void run()}>让本机助手做</button>
        </div>
        {refused && <p className="error">{refused}</p>}
        {result && (
          <div aria-label="本机结果">
            <pre style={{ whiteSpace: 'pre-wrap' }}>{result.output}</pre>
            <p className="muted">{result.notice}</p>
            {outgoing && (
              <div className="card" aria-label="同步前脱敏">
                <p>要放进云端知识库吗？发出去的是下面这份（已脱敏）：</p>
                <pre style={{ whiteSpace: 'pre-wrap' }}>{outgoing.text}</pre>
                <p className="muted">{outgoing.hits.length ? `遮掉了：${outgoing.hits.map((h) => `${REDACT_NAMES[h.kind]} ${h.count} 处`).join('、')}` : '没有找到需要遮的号码；人名、地址请你自己看一遍'}</p>
                <label><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> 我看过了，可以发到云端</label>
                <button disabled={!confirm} onClick={() => void sync()}>放进我的知识库</button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card" aria-label="本机笔记">
        <h4>本机笔记（{notes.length}）</h4>
        {notes.length === 0 && <p className="muted">还没有。本机笔记只存在这个浏览器里，清除浏览器数据就没了。</p>}
        <ul className="list">
          {notes.map((n) => (
            <li key={n.id}>
              <button className="text-link" onClick={() => setText(n.text)}>{n.text.slice(0, 40)}{n.text.length > 40 ? '…' : ''}</button>
              {' '}<button className="text-link" aria-label="删掉这条本机笔记" onClick={() => removeNote(n.id)}>×</button>
            </li>
          ))}
        </ul>
      </div>

      <div className="card" aria-label="端侧模型">
        <h4>端侧模型</h4>
        <p className="muted">{catalog?.note ?? ''} 浏览器里不下载模型，用的是本机规则；在手机 App 的「隐私沙箱」里可以下载。</p>
        {catalog && catalog.items.length === 0 && <p className="muted">平台还没有上架端侧模型。</p>}
        <ul className="list">
          {catalog?.items.map((m) => (
            <li key={m.id}><strong>{m.name}</strong>
              <span className="muted"> · {m.params_b}B · {m.quant} · {m.size_mb} MB · 至少 {m.min_ram_gb} GB 内存 · {m.license} · sha256 {m.sha256.slice(0, 12)}…</span></li>
          ))}
        </ul>
      </div>
    </div>
  );
}
