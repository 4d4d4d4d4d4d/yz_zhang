import {
  apiErrorText, formatDateTime,
  type ApiKeyView, type WebhookDeliveryView, type WebhookView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

/** UI-076/077 开发者设置（54 号 spec 的界面侧）。
 *
 * 两条硬要求：明文密钥**只显示一次**这件事必须说出来（库里只有哈希，
 * 界面也拿不回来）；Webhook 被自动停用时**必须显示原因**——
 * 悄悄停掉比不停更坏，集成方会以为平台还在发。
 */
export default function Developer() {
  const { client } = useApp();
  const [keys, setKeys] = useState<ApiKeyView[]>([]);
  const [hooks, setHooks] = useState<WebhookView[]>([]);
  const [scopes, setScopes] = useState<Array<{ name: string; description: string }>>([]);
  const [scopeNote, setScopeNote] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [keyName, setKeyName] = useState('');
  const [plain, setPlain] = useState<{ key: string; warning: string } | null>(null);
  const [hookUrl, setHookUrl] = useState('');
  const [hookEvents, setHookEvents] = useState('task.completed');
  const [secret, setSecret] = useState<{ secret: string; howto: string } | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDeliveryView[] | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setKeys(await client.apiKeys().catch(() => []));
    setHooks(await client.webhooks().catch(() => []));
    const s = await client.apiScopes().catch(() => null);
    if (s) { setScopes(s.scopes); setScopeNote(s.note); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (err) { setError(apiErrorText(err)); }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>API 密钥</h3>
        {/* scope 说明来自服务端：能给哪些权限是平台的决定，不是前端的清单 */}
        {scopeNote && <p className="muted" data-testid="scope-note">{scopeNote}</p>}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <input className="grow" placeholder="密钥名称（给自己看的）" value={keyName}
                 onChange={(e) => setKeyName(e.target.value)} />
          <button disabled={picked.length === 0}
                  onClick={() => act(async () => {
                    const r = await client.createApiKey(keyName || '未命名', picked);
                    setPlain({ key: r.key, warning: r.warning });
                    setKeyName(''); setPicked([]);
                  })}>
            生成密钥
          </button>
        </div>
        <div className="row">
          {scopes.map((s) => (
            <label key={s.name} className="row" style={{ gap: 4 }} title={s.description}>
              <input type="checkbox" style={{ width: 'auto' }} checked={picked.includes(s.name)}
                     onChange={(e) => setPicked(e.target.checked
                       ? [...picked, s.name]
                       : picked.filter((x) => x !== s.name))} />
              {s.name}
            </label>
          ))}
        </div>

        {/* UI-076 明文只出现这一次，界面必须说出来 */}
        {plain && (
          <div className="card" data-testid="plain-key" style={{ marginTop: 12 }}>
            <p className="error">{plain.warning}</p>
            <pre className="agent-output">{plain.key}</pre>
            <button className="ghost" onClick={() => setPlain(null)}>我已复制，关闭</button>
          </div>
        )}

        <div className="list" style={{ marginTop: 12 }}>
          {keys.length === 0 && <p className="muted">还没有密钥。</p>}
          {keys.map((k) => (
            <div className="task-item" key={k.id}>
              <div>
                <strong>{k.name}</strong> <span className="muted">{k.key_prefix}…</span>
                <p className="muted">
                  {k.scopes.join(' / ') || '无权限'} ·
                  {k.active ? ' 生效中' : ' 已吊销'} ·
                  最近使用 {k.last_used_at ? formatDateTime(k.last_used_at) : '从未'}
                </p>
              </div>
              {k.active && (
                <span className="row">
                  <button className="ghost" onClick={() => act(async () => {
                    const r = await client.rotateApiKey(k.id);
                    setPlain({ key: r.key, warning: r.warning });
                  })}>轮换</button>
                  <button className="danger" onClick={() => act(() => client.revokeApiKey(k.id))}>吊销</button>
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Webhook</h3>
        <div className="row">
          <input className="grow" placeholder="https://你的服务/回调" value={hookUrl}
                 onChange={(e) => setHookUrl(e.target.value)} />
          <input style={{ width: 200 }} placeholder="事件（逗号分隔）" value={hookEvents}
                 onChange={(e) => setHookEvents(e.target.value)} />
          <button disabled={hookUrl.length < 8} onClick={() => act(async () => {
            const r = await client.createWebhook(
              hookUrl, hookEvents.split(',').map((s) => s.trim()).filter(Boolean),
            );
            setSecret({ secret: r.secret, howto: r.signature_howto });
            setHookUrl('');
          })}>登记</button>
        </div>
        {secret && (
          <div className="card" data-testid="hook-secret" style={{ marginTop: 12 }}>
            <pre className="agent-output">{secret.secret}</pre>
            <p className="muted">{secret.howto}</p>
            <button className="ghost" onClick={() => setSecret(null)}>知道了</button>
          </div>
        )}
        <div className="list" style={{ marginTop: 12 }}>
          {hooks.length === 0 && <p className="muted">还没有 Webhook。</p>}
          {hooks.map((h) => (
            <div className="task-item" key={h.id}>
              <div>
                <strong>{h.url}</strong>
                <p className="muted">{h.events.join(' / ')} · 连续失败 {h.consecutive_failures} 次</p>
                {/* UI-077 自动停用必须说明原因：悄悄停掉比不停更坏 */}
                {!h.active && (
                  <p className="error" data-testid="hook-disabled">
                    已停用：{h.disabled_reason || '未说明原因'}
                  </p>
                )}
              </div>
              <span className="row">
                <button className="ghost" onClick={() => act(async () => {
                  setDeliveries(await client.webhookDeliveries(h.id));
                })}>投递记录</button>
                <button className="danger" onClick={() => act(() => client.deleteWebhook(h.id))}>删除</button>
              </span>
            </div>
          ))}
        </div>
        {deliveries && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>事件</th><th>状态</th><th>尝试</th><th>响应</th><th>时间</th></tr></thead>
            <tbody>
              {deliveries.map((d) => (
                <tr key={d.id}>
                  <td>{d.event_type}</td>
                  <td>{d.status}</td>
                  <td>{d.attempts}</td>
                  <td className="muted">{d.response_code ?? '—'} {d.response_excerpt}</td>
                  <td className="muted">{formatDateTime(d.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
