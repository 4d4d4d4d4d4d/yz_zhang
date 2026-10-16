import { apiErrorText, formatDateTime, type AdminList, type AdminRoleCatalog, type AdminRoleKey } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** SEC-061b 管理员与角色（141 号 spec）：每位管理员看得到自己的角色；超级管理员能给别人分配。
 *  拦在服务端，这里只是让人知道自己能做什么、该找谁加权限。 */
export function AdminRolesPanel() {
  const { client } = useApp();
  const [catalog, setCatalog] = useState<AdminRoleCatalog | null>(null);
  const [list, setList] = useState<AdminList | null>(null);
  const [draft, setDraft] = useState<Record<number, AdminRoleKey[]>>({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      const c = await client.adminRoleCatalog();
      setCatalog(c && Array.isArray(c.roles) ? c : null);
      if (c?.mine?.includes('super')) {
        const l = await client.listAdmins();
        setList(l && Array.isArray(l.admins) ? l : null);
      }
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  if (!catalog) return error ? <p className="error">{error}</p> : null;
  const label = (k: string) => catalog.roles.find((r) => r.key === k)?.label ?? k;
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const toggle = (uid: number, cur: AdminRoleKey[], k: AdminRoleKey) => {
    const base = draft[uid] ?? cur;
    setDraft({ ...draft, [uid]: base.includes(k) ? base.filter((x) => x !== k) : [...base, k] });
  };
  return (
    <div className="card" aria-label="管理员与角色">
      <h3>管理员与角色</h3>
      <p>我的角色：{catalog.mine.map(label).join('、')}</p>
      <ul className="muted">{catalog.roles.map((r) => <li key={r.key}><strong>{r.label}</strong>：{r.scope}</li>)}</ul>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {list && (
        <>
          {list.unclassified > 0 && (
            <p className="error">还有 {list.unclassified} 位管理员没分配角色，按超级管理员对待（全权）。上线前请逐个分好。</p>
          )}
          <table>
            <thead><tr><th>管理员</th>{catalog.roles.map((r) => <th key={r.key}>{r.label}</th>)}<th /></tr></thead>
            <tbody>
              {list.admins.map((a) => {
                const cur = draft[a.user_id] ?? (a.unclassified ? [] : a.roles);
                return (
                  <tr key={a.user_id}>
                    <td>{a.nickname || `#${a.user_id}`}{a.unclassified && <span className="badge">未分级</span>}
                      {/* SEC-061e（171 号 spec）临时角色：到点自动失效，可提前收回 */}
                      {(a.temporary ?? []).map((t) => (
                        <div key={t.role} className="muted" data-testid={`temp-role-${a.user_id}-${t.role}`}>
                          {label(t.role)}（临时，到 {formatDateTime(t.until)}）
                          <button className="text-link" onClick={() => void act(() => client.revokeTemporaryAdminRole(a.user_id, t.role), `已收回「${label(t.role)}」`)}>提前收回</button>
                        </div>
                      ))}
                      {!a.unclassified && (
                        <button className="text-link" onClick={() => {
                          const role = window.prompt(`临时给哪个角色？（${catalog.roles.filter((r) => r.key !== 'super').map((r) => r.key).join(' / ')}）`);
                          const hours = role ? window.prompt('多少小时后自动失效？（1~720）', '48') : null;
                          const reason = hours ? window.prompt('理由（会进审计，也会告诉他）') : null;
                          if (role && hours && reason) void act(() => client.grantTemporaryAdminRole(a.user_id, role.trim() as AdminRoleKey, parseInt(hours, 10), reason.trim()), `已临时授予「${label(role.trim())}」`);
                        }}>临时授予</button>
                      )}</td>
                    {catalog.roles.map((r) => (
                      <td key={r.key}>
                        <input type="checkbox" aria-label={`${a.nickname || a.user_id} ${r.label}`} checked={cur.includes(r.key)}
                          onChange={() => toggle(a.user_id, cur, r.key)} />
                      </td>
                    ))}
                    <td>
                      <button disabled={!draft[a.user_id]?.length} onClick={() => void (async () => {
                        setError(''); setNotice('');
                        try {
                          const row = await client.setAdminRoles(a.user_id, draft[a.user_id]);
                          setNotice(`已更新「${row.nickname || row.user_id}」的角色：${row.roles.map(label).join('、')}`);
                          setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => Number(k) !== a.user_id)));
                          await load();
                        } catch (e) { setError(apiErrorText(e)); }
                      })()}>保存</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
