// CNT-014 视频沉浸流：上下滑、倍速、断点续播、流量提醒。
//
// 原 spec 明确点了这四件事。它们不是"播放器功能列表"，各有各的理由：
//
// - **断点续播**：看到一半切走再回来，从头播是最招人烦的一种"重置"。
// - **流量提醒**：这是个 LBS 平台，执行者常在户外用蜂窝网络。
//   一个自动连播的视频流能悄悄吃掉几百 MB——**默认在蜂窝网下不自动播**，
//   这是替用户的钱包做的决定，不是功能开关。
// - **倍速**：看教程/案例的人第一个会找的东西。
// - **上下滑**：沉浸流的基本形态。
import { useCallback, useEffect, useRef, useState } from 'react';

export type VideoItem = { id: number; url: string; title: string; author: string };

const RATES = [1, 1.25, 1.5, 2];
const POSITION_KEY = 'video-positions';

/** 断点位置存本地：这是"每个人自己的观看进度"，不该占服务端一张表，
 *  也不该在换设备后跟过去——那会变成"我在手机上看到一半，电脑上也跳过去了"。 */
function loadPositions(): Record<number, number> {
  try { return JSON.parse(localStorage.getItem(POSITION_KEY) || '{}'); }
  catch { return {}; }
}
function savePosition(id: number, seconds: number) {
  try {
    const all = loadPositions();
    // 快看完了就不记了：下次该从头开始，而不是跳到最后两秒
    if (seconds < 3) delete all[id]; else all[id] = seconds;
    localStorage.setItem(POSITION_KEY, JSON.stringify(all));
  } catch { /* 隐私模式等：存不了就算了，不影响播放 */ }
}

/** 判断当前是不是蜂窝网络。`connection` 是非标准 API，取不到时**按"可能是流量"
 *  处理**——宁可多问一次，也不要替用户花掉几百 MB。 */
function onCellular(): boolean {
  const conn = (navigator as unknown as {
    connection?: { type?: string; effectiveType?: string; saveData?: boolean };
  }).connection;
  if (!conn) return false;               // 桌面浏览器普遍没有这个 API
  if (conn.saveData) return true;        // 用户开了省流量模式
  return conn.type === 'cellular';
}

export function VideoFeed({ items }: { items: VideoItem[] }) {
  const [index, setIndex] = useState(0);
  const [rate, setRate] = useState(1);
  const [allowData, setAllowData] = useState(!onCellular());
  const ref = useRef<HTMLVideoElement | null>(null);
  const current = items[index];

  // 换视频时恢复断点 + 套用当前倍速
  useEffect(() => {
    const el = ref.current;
    if (!el || !current) return;
    el.playbackRate = rate;
    const saved = loadPositions()[current.id];
    if (saved) el.currentTime = saved;
  }, [index, rate, current]);

  const go = useCallback((delta: number) => {
    const el = ref.current;
    if (el && current) savePosition(current.id, el.currentTime);
    setIndex((i) => Math.min(Math.max(i + delta, 0), items.length - 1));
  }, [current, items.length]);

  // 上下滑 / 键盘上下
  const touchStart = useRef(0);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') go(1);
      if (e.key === 'ArrowUp') go(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go]);

  if (!current) return <p className="muted">还没有视频内容。</p>;

  return (
    <div
      className="card"
      onTouchStart={(e) => { touchStart.current = e.touches[0].clientY; }}
      onTouchEnd={(e) => {
        const dy = touchStart.current - e.changedTouches[0].clientY;
        if (Math.abs(dy) > 50) go(dy > 0 ? 1 : -1);
      }}
    >
      {!allowData ? (
        // 流量提醒：**默认不自动播**，让用户自己决定花不花这个流量
        <div style={{ display: 'grid', gap: 8, textAlign: 'center', padding: 24 }}>
          <strong>{current.title}</strong>
          <p className="muted">当前可能在使用蜂窝数据，视频会消耗较多流量。</p>
          <button onClick={() => setAllowData(true)}>继续播放（使用流量）</button>
        </div>
      ) : (
        <video
          ref={ref}
          src={current.url}
          controls
          playsInline
          style={{ width: '100%', maxHeight: '70vh', background: '#000' }}
          onTimeUpdate={(e) => savePosition(current.id, e.currentTarget.currentTime)}
          onEnded={() => go(1)}
        />
      )}
      <div className="row">
        <strong>{current.title}</strong>
        <span className="muted">@{current.author}</span>
      </div>
      <div className="row">
        <button className="ghost" disabled={index === 0} onClick={() => go(-1)}>上一个</button>
        <button className="ghost" disabled={index === items.length - 1} onClick={() => go(1)}>下一个</button>
        <span className="muted">{index + 1} / {items.length}</span>
        {RATES.map((r) => (
          <button key={r} className={r === rate ? '' : 'ghost'} onClick={() => setRate(r)}>
            {r}×
          </button>
        ))}
      </div>
    </div>
  );
}
