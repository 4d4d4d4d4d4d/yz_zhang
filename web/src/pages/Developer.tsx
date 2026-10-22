import {
  apiErrorText, formatDateTime,
  type ApiKeyUsageView, type ApiKeyView, type ApiQuotaRequest, type WebhookDeliveryView, type WebhookView, accountQuotaNote,
  quotaRequestLine } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';
import MachineMandate from '../MachineMandate';

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
                {k.scopes.includes('tasks:write') && k.active && <MachineMandate client={client} keyId={k.id} />}
                {k.active && typeof k.effective_rate_per_minute === 'number' && (
                  <KeyRate keyId={k.id} own={k.rate_per_minute} effective={k.effective_rate_per_minute}
                           onSave={(n) => act(() => client.setApiKeyRate(k.id, n))} />
                )}
                {/* API-052 用量与每日配额（152 号 spec） */}
                {k.active && <KeyUsage keyId={k.id} />}
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

      {/* API-057（241 号 spec）有 Key 才能申请提额 */}
      {keys.length > 0 && <QuotaRequests />}

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

/** API-050 每把 Key 的每分钟上限（145 号 spec）：超了回 429 并带 Retry-After；只能设得比平台默认低，0 = 恢复默认。 */
/** API-052 今天用了多少、还剩多少、几点恢复；最近 14 天每天进来多少、挡回去多少；可设更低的每日配额 */
function KeyUsage({ keyId }: { keyId: number }) {
  const { client } = useApp();
  const [u, setU] = useState<ApiKeyUsageView | null>(null);
  const [v, setV] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setU(await client.apiKeyUsage(keyId)); } catch (e) { setError(apiErrorText(e)); }
  }, [client, keyId]);
  useEffect(() => { void load(); }, [load]);
  // 载荷不对就不显示这一块，别把整个开发者页拖白
  if (!u || !Array.isArray(u.days)) return error ? <p className="error">{error}</p> : null;
  const peak = Math.max(1, ...u.days.map((d) => d.count + d.rejected));
  return (
    <div data-testid={`key-usage-${keyId}`}>
      <p className="muted row">
        今天（{u.time_zone}）已用 {u.today_used} / {u.effective_daily_quota} 次{u.daily_quota ? '（你设的配额）' : '（平台默认配额）'}，
        还剩 {u.today_remaining} 次，{formatDateTime(u.resets_at)} 恢复
        {/* API-054（158 号 spec） */}
        {typeof u.account_daily_quota === 'number' && `；账号下所有 Key 合计 ${u.account_today_used} / ${u.account_daily_quota} 次`}
        {/* API-056（235 号 spec） */}
        {accountQuotaNote(u) && `（${accountQuotaNote(u)}）`} ·
        <input style={{ width: 110 }} aria-label={`Key ${keyId} 每日配额`} type="number" min={0} placeholder="设更低的配额" value={v}
               onChange={(e) => setV(e.target.value)} />
        <button className="ghost" disabled={v === ''} onClick={async () => {
          setError('');
          try { await client.setApiKeyQuota(keyId, Number(v)); setV(''); await load(); } catch (e) { setError(apiErrorText(e)); }
        }}>保存配额</button>
      </p>
      <table aria-label={`Key ${keyId} 最近用量`}>
        <thead><tr><th>日期</th><th>进来</th><th>挡回</th><th></th></tr></thead>
        <tbody>
          {u.days.map((d) => (
            <tr key={d.day}>
              <td>{d.day}</td><td>{d.count}</td><td>{d.rejected || ''}</td>
              <td><div style={{ height: 6, width: `${Math.round(((d.count + d.rejected) / peak) * 120)}px`, background: d.rejected ? '#f59e0b' : '#3b82f6' }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function KeyRate({ keyId, own, effective, onSave }: { keyId: number; own: number; effective: number; onSave: (n: number) => void }) {
  const [v, setV] = useState('');
  return (
    <p className="muted row" data-testid={`key-rate-${keyId}`}>
      每分钟最多 {effective} 次{own ? '（你设的）' : '（平台默认）'}，超了会收到 429 并告诉你几秒后重试 ·
      <input style={{ width: 90 }} aria-label={`Key ${keyId} 每分钟上限`} type="number" min={0} placeholder="设更低" value={v}
             onChange={(e) => setV(e.target.value)} />
      <button className="ghost" disabled={v === ''} onClick={() => { onSave(Number(v)); setV(''); }}>保存</button>
    </p>
  );
}

/** API-057（241 号 spec）申请提高账号每日总配额：写想要多少、多少天、干什么用；运营批或驳回后在这里看到结果。 */
function QuotaRequests() {
  const { client } = useApp();
  const [rows, setRows] = useState<ApiQuotaRequest[]>([]);
  const [quota, setQuota] = useState('');
  const [days, setDays] = useState('');
  const [purpose, setPurpose] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const r = await client.myApiQuotaRequests().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  const pending = rows.some((r) => r.status === 'pending');
  async function submit() {
    const q = Number(quota), d = days ? Number(days) : undefined, p = purpose.trim();
    setError(''); setNotice('');
    try {
      await client.requestApiQuota(q, p, d);
      setQuota(''); setDays(''); setPurpose('');
      setNotice('已提交：运营会看你的用途与最近的用量，批了或没批都会通知你');
      await load();
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card" aria-label="申请提高配额">
      <h3>申请提高账号配额</h3>
      <p className="muted">账号下所有 Key 合计每天有上限。用量要变大时写清想要多少、多少天、干什么用，运营批了立刻生效。</p>
      {!pending && (
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          <input aria-label="想要的每日配额" type="number" min={1} placeholder="每天多少次" value={quota} onChange={(e) => setQuota(e.target.value)} style={{ width: 130 }} />
          <input aria-label="想要多少天" type="number" min={1} max={366} placeholder="多少天（空 = 长期）" value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 160 }} />
          <input aria-label="用途" className="grow" placeholder="用途（至少 10 个字：接什么系统、每天大概调用哪些接口）" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
          <button disabled={!quota || purpose.trim().length < 10} onClick={() => void submit()}>提交申请</button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <ul>
        {rows.map((r) => (
          <li key={r.id} data-testid={`quota-request-${r.id}`}>
            {quotaRequestLine(r)}
            {r.status === 'pending' && <> <button className="text-link" onClick={async () => {
              setError(''); setNotice('');
              try { await client.withdrawApiQuotaRequest(r.id); setNotice('已撤回'); await load(); } catch (e) { setError(apiErrorText(e)); }
            }}>撤回</button></>}
          </li>
        ))}
      </ul>
    </div>
  );
}
