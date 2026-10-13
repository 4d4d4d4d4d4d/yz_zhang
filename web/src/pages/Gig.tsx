import {
  apiErrorText, fmtYuan, formatDateTime,
  type GigAlong, type GigAvailabilityView, type GigNearby, type GigPlaceRow, type GigQuote, type GigTaskCard,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../store';

/** GIG-100 接单（125 号 spec）：现在有空就推附近的新单、上下班顺路带一单、报价前看行情。
 *
 * 位置只用到约 1 公里精度；「现在有空」到点自动关掉，位置随之删除。距离都是直线估算。
 */
type Here = { lat: number; lng: number };

function locate(): Promise<Here> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error('这个浏览器拿不到位置')); return; }
    navigator.geolocation.getCurrentPosition((p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => reject(new Error('没拿到位置：请允许浏览器使用定位')));
  });
}

export default function Gig() {
  const { client } = useApp();
  const [avail, setAvail] = useState<GigAvailabilityView | null>(null);
  const [radius, setRadius] = useState(5);
  const [hours, setHours] = useState(2);
  const [cats, setCats] = useState('');
  const [near, setNear] = useState<GigNearby | null>(null);
  const [places, setPlaces] = useState<GigPlaceRow[]>([]);
  const [along, setAlong] = useState<GigAlong | null>(null);
  const [route, setRoute] = useState<{ from: string; to: string; detour: number }>({ from: 'here', to: '', detour: 2 });
  const [quote, setQuote] = useState<GigQuote | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const a = await client.gigAvailability();
      setAvail(a);
      setPlaces(await client.gigPlaces());
      setNear(a.available ? await client.gigNearby() : null);
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<string | void>) {
    setError(''); setNotice('');
    try { const msg = await fn(); if (msg) setNotice(msg); await load(); } catch (e) { setError(e instanceof Error && !('code' in e) ? e.message : apiErrorText(e)); }
  }
  async function findAlong() {
    setError('');
    try {
      const to = Number(route.to);
      if (route.from === 'here') {
        const here = await locate();
        setAlong(await client.gigAlong({ to_place: to, from_lat: here.lat, from_lng: here.lng, max_detour_km: route.detour }));
      } else {
        setAlong(await client.gigAlong({ to_place: to, from_place: Number(route.from), max_detour_km: route.detour }));
      }
    } catch (e) { setError(e instanceof Error && !('code' in e) ? e.message : apiErrorText(e)); }
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>接单</h2>
        <p className="muted">有空就接附近的单，路上顺手带一单，报价前看看行情。位置只用到约 1 公里，距离是直线估算。<Link to="/packs?pack=gig-nearby">问接单助手</Link></p>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <div className="card" aria-label="现在有空">
        {avail?.available ? (
          <div className="row">
            <strong className="grow">现在有空：{avail.radius_km} 公里内，到 {formatDateTime(avail.until)}{avail.categories.length ? `，只看 ${avail.categories.join('、')}` : ''}（已推 {avail.pushed} 条）</strong>
            <button className="ghost" onClick={() => void act(async () => { await client.stopGigAvailable(); setNear(null); return '已关掉，位置已删除'; })}>不接了</button>
          </div>
        ) : (
          <div className="row">
            <label>能走多远 <select aria-label="半径" value={radius} onChange={(e) => setRadius(Number(e.target.value))}>
              {[1, 3, 5, 10, 20].map((n) => <option key={n} value={n}>{n} 公里</option>)}</select></label>
            <label>有空多久 <select aria-label="时长" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              {[1, 2, 4, 8].map((n) => <option key={n} value={n}>{n} 小时</option>)}</select></label>
            <input className="grow" aria-label="只看这些类目" placeholder="只看这些类目（空格分开，可不填）" value={cats} onChange={(e) => setCats(e.target.value)} />
            <button onClick={() => void act(async () => {
              const here = await locate();
              await client.setGigAvailable({ ...here, radius_km: radius, hours, categories: cats.split(/[\s,，]+/).filter(Boolean) });
              return `好的：接下来 ${hours} 小时附近有新单就推给你`;
            })}>我现在有空</button>
          </div>
        )}
        {near && <TaskList items={near.items} empty="附近暂时没有招募中的单，有新单会推给你" onQuote={(id) => void client.gigQuote({ task_id: id }).then(setQuote).catch((e) => setError(apiErrorText(e)))} />}
      </div>

      <div className="card" aria-label="顺路单">
        <h4>顺路单</h4>
        <div className="row">
          {places.map((p) => (
            <span key={p.id} className="badge">{p.name} <button className="text-link" aria-label={`删掉地点：${p.name}`}
              onClick={() => void act(async () => { await client.deleteGigPlace(p.id); return '已删除'; })}>×</button></span>
          ))}
          {['家', '公司'].filter((n) => !places.some((p) => p.name === n)).map((n) => (
            <button key={n} className="ghost" onClick={() => void act(async () => {
              const here = await locate();
              await client.addGigPlace(n, here.lat, here.lng);
              return `已把这里存为「${n}」`;
            })}>把这里存为「{n}」</button>
          ))}
        </div>
        {places.length > 0 && (
          <div className="row">
            <label>从 <select aria-label="起点" value={route.from} onChange={(e) => setRoute({ ...route, from: e.target.value })}>
              <option value="here">当前位置</option>{places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label>到 <select aria-label="终点" value={route.to} onChange={(e) => setRoute({ ...route, to: e.target.value })}>
              <option value="">选一个</option>{places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <label>最多多走 <select aria-label="最多多走" value={route.detour} onChange={(e) => setRoute({ ...route, detour: Number(e.target.value) })}>
              {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n} 公里</option>)}</select></label>
            <button disabled={!route.to} onClick={() => void findAlong()}>看看顺路的单</button>
          </div>
        )}
        {along && <TaskList items={along.items} empty={`去「${along.to}」的路上，多走 ${along.max_detour_km} 公里以内暂时没有单`}
          onQuote={(id) => void client.gigQuote({ task_id: id }).then(setQuote).catch((e) => setError(apiErrorText(e)))} />}
      </div>

      {quote && (
        <div className="card" aria-label="报价参考">
          <h4>报价参考{quote.category ? `：${quote.category}` : ''}</h4>
          <ul>{quote.basis.map((b) => <li key={b}>{b}</li>)}</ul>
          <p className="muted">{quote.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

function TaskList({ items, empty, onQuote }: { items: GigTaskCard[]; empty: string; onQuote: (id: number) => void }) {
  if (!items.length) return <p className="muted">{empty}</p>;
  return (
    <ul className="list">
      {items.map((t) => (
        <li key={t.task_id}>
          <Link to={`/tasks/${t.task_id}`}>{t.title}</Link>
          <span className="muted"> · {t.category} · {t.address_hint}
            {t.distance_m !== undefined && ` · 约 ${(t.distance_m / 1000).toFixed(1)} 公里`}
            {t.detour_m !== undefined && ` · 多走约 ${(t.detour_m / 1000).toFixed(1)} 公里`}
            {' · '}预算 {fmtYuan(t.budget_cents)}，到手约 {fmtYuan(t.net_cents)}</span>
          {' '}<button className="text-link" onClick={() => onQuote(t.task_id)}>看行情</button>
        </li>
      ))}
    </ul>
  );
}
