import { apiErrorText, formatDateTime, type Notice, type NotificationPrefsView } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function Notifications() {
  const { client } = useApp();
  const [notes, setNotes] = useState<Notice[]>([]);
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    setNotes(await client.notifications());
    setUnread((await client.unreadCount().catch(() => ({ unread: 0 }))).unread);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="page">
      <NotificationSwitches />
      <div className="card">
        <div className="row">
          <h3 className="grow">通知中心{unread > 0 ? `（未读 ${unread}）` : ''}</h3>
          {unread > 0 && (
            <button className="ghost"
                    onClick={async () => { await client.markAllRead(); await load(); }}>全部标为已读</button>
          )}
        </div>
        <div className="list" style={{ marginTop: 8 }}>
          {notes.length === 0 && <p className="muted">暂无通知</p>}
          {notes.map((n) => (
            <div key={n.id} className="task-item" style={{ opacity: n.is_read ? 0.55 : 1 }}>
              <div>
                <strong>{n.title}</strong> <span className="badge">{n.category}</span>
                <p className="muted">{n.body} · {formatDateTime(n.created_at)}</p>
              </div>
              {!n.is_read && (
                <button className="ghost" onClick={async () => { await client.markRead(n.id); await load(); }}>已读</button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** NTF-065 通知开关（77 号 spec）。
 *
 * 65 号那张 `MUST_REACH` 表的全部论证建立在「用户能关掉别的通知」之上——
 * 而那个开关**两端都没有**。一条用来做减法的规矩，减的是一个不存在的东西。
 *
 * 「哪些关不掉」**来自服务端**：那张表会变（V65 立、V100 加过一行），
 * 界面里抄一份，它第二天就过期了。
 */
function NotificationSwitches() {
  const { client } = useApp();
  const [view, setView] = useState<NotificationPrefsView | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const v = await client.notificationPrefs().catch(() => null);
    setView(v && v.prefs ? v : null);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function toggle(category: string, enabled: boolean) {
    setError('');
    try {
      await client.setNotificationPref(category, enabled);
      await load();
    } catch (err) {
      // funds 类关不掉，服务端的理由原样显示（不在界面里另写一句）
      setError(apiErrorText(err));
    }
  }

  if (!view) return null;
  return (
    <div className="card">
      <h3>通知偏好</h3>
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {Object.entries(view.prefs).map(([category, enabled]) => (
          <label key={category} className="row" data-testid={`pref-${category}`}>
            <input type="checkbox" checked={enabled}
                   onChange={(e) => void toggle(category, e.target.checked)} />
            <span className="grow">{category}</span>
          </label>
        ))}
      </div>
      <h4 style={{ marginTop: 12 }}>以下通知不受开关影响</h4>
      <p className="muted">
        资金类（{view.always_on_categories.join('、')}）一律送达；
        另外这几条错过就无法挽回：
      </p>
      <ul className="muted">
        {view.always_on.map((a) => (
          <li key={`${a.category}/${a.title}`} data-testid={`always-on-${a.title}`}>
            <strong>{a.title}</strong>（{a.category}）：{a.why}
          </li>
        ))}
      </ul>
    </div>
  );
}
