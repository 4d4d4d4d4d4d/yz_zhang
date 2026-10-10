import { apiErrorText, TASK_STATUS_LABEL, fmtYuan, type Task } from '@platform/core';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ParallaxHero, Reveal } from '../Motion';
import { useApp } from '../store';

const CATEGORIES = ['', '保洁', '跑腿', '维修', '软件开发', '设计', '活动策划', '二手交易'];

export default function Square() {
  const { client, hasToken } = useApp();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [nearby, setNearby] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load(lat?: number, lng?: number) {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string | number | undefined> = { q: q || undefined, category: category || undefined };
      if (lat !== undefined) {
        params.lat = lat;
        params.lng = lng;
        params.max_km = 10;
      }
      setTasks(await client.listTasks(params));
    } catch (err) {
      setError(apiErrorText(err));
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
    <div className="page square-page">
      {/* PRLX 视差 hero 只用在「没有按钮在被按」的地方：
          广场是浏览页，钱包/提现/签署那些页面刻意不加（79 号 spec） */}
      <div className="page-heading"><span className="eyebrow">OPPORTUNITIES / 01</span><span className="muted">每一种能力，都有新的可能</span></div>
      <ParallaxHero title={'让能力相遇，\n让合作发生。'}
                    subtitle="连接独立个体、专业组织与智能助理。从一个任务开始，一起把想法变成成果。">
        <div className="hero-actions"><Link className="button-link" to={hasToken ? '/publish' : '/login'}>发布一个任务 <span aria-hidden="true">↗</span></Link><Link className="text-link" to={hasToken ? '/ventures' : '/login'}>组建合作体 →</Link></div>
        <div className="hero-tags"><span>人 × 人</span><span>人 × 智能体</span><span>跨组织协作</span></div>
      </ParallaxHero>
      <div className="section-heading"><div><span className="eyebrow">FIND YOUR NEXT COLLABORATION</span><h2>任务广场</h2></div><span className="muted">从生活服务到专业创造</span></div>
      <div className="card row search-toolbar">
        <input className="grow" placeholder="搜索任务…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: 140 }}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c || '全部类目'}</option>
          ))}
        </select>
        <button onClick={() => void load()}>搜索</button>
        <button className="ghost" onClick={toggleNearby}>{nearby ? '取消附近' : '📍 附近 10km'}</button>
        {hasToken && category && (
          <button className="ghost" title="该类目新任务发布时通知我"
                  onClick={async () => {
                    try { await client.subscribeCategory(category); alert(`已订阅「${category}」，新任务会通知你`); } catch (err) { setError(apiErrorText(err)); }
                  }}>
            🔔 订阅类目
          </button>
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="list opportunity-grid">
        {loading && <p className="muted">加载中…</p>}
        {!loading && tasks.length === 0 && <div className="card muted">暂无任务，去发布第一个吧</div>}
        {tasks.map((t, i) => (
          <Reveal key={t.id} delayMs={Math.min(i, 6) * 40}>
          <div className="card task-item opportunity-card">
            <div className="task-category"><span>{t.category}</span><span>{t.is_remote ? '远程协作' : '本地服务'}</span></div>
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
          </Reveal>
        ))}
      </div>
    </div>
  );
}
