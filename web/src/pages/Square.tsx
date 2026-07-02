import { TASK_STATUS_LABEL, fmtYuan, type Task } from '@platform/core';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../store';

const CATEGORIES = ['', '保洁', '跑腿', '维修', '软件开发', '设计', '活动策划', '二手交易'];

export default function Square() {
  const { client, hasToken } = useApp();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [nearby, setNearby] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load(lat?: number, lng?: number) {
    setLoading(true);
    try {
      const params: Record<string, string | number | undefined> = { q: q || undefined, category: category || undefined };
      if (lat !== undefined) {
        params.lat = lat;
        params.lng = lng;
        params.max_km = 10;
      }
      setTasks(await client.listTasks(params));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  function toggleNearby() {
    if (!nearby && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setNearby(true);
          void load(pos.coords.latitude, pos.coords.longitude);
        },
        () => alert('定位失败，已展示全部任务'),
      );
    } else {
      setNearby(false);
      void load();
    }
  }

  return (
    <div className="page">
      <div className="card row">
        <input className="grow" placeholder="搜索任务…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: 140 }}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c || '全部类目'}</option>
          ))}
        </select>
        <button onClick={() => void load()}>搜索</button>
        <button className="ghost" onClick={toggleNearby}>{nearby ? '取消附近' : '📍 附近 10km'}</button>
      </div>
      <div className="list">
        {loading && <p className="muted">加载中…</p>}
        {!loading && tasks.length === 0 && <div className="card muted">暂无任务，去发布第一个吧</div>}
        {tasks.map((t) => (
          <div className="card task-item" key={t.id}>
            <div>
              <Link to={hasToken ? `/tasks/${t.id}` : '/login'}><strong>{t.title}</strong></Link>
              <p className="muted">
                {t.category} · {t.is_remote ? '线上' : `${t.city} ${t.address_hint}`}
                {t.distance_m != null && ` · ${(t.distance_m / 1000).toFixed(1)}km`}
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="price">{fmtYuan(t.budget_cents)}</div>
              <span className="badge">{TASK_STATUS_LABEL[t.status]}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
