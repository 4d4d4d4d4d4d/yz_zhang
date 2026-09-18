import { type Notice } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function Notifications() {
  const { client } = useApp();
  const [notes, setNotes] = useState<Notice[]>([]);

  const load = useCallback(async () => setNotes(await client.notifications()), [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="page">
      <div className="card">
        <h3>通知中心</h3>
        <div className="list" style={{ marginTop: 8 }}>
          {notes.length === 0 && <p className="muted">暂无通知</p>}
          {notes.map((n) => (
            <div key={n.id} className="task-item" style={{ opacity: n.is_read ? 0.55 : 1 }}>
              <div>
                <strong>{n.title}</strong> <span className="badge">{n.category}</span>
                <p className="muted">{n.body} · {new Date(n.created_at).toLocaleString()}</p>
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
