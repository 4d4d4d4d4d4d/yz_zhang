// MOB-002 底部 Tab 导航（手机可见，桌面由 CSS 隐藏）。
// 未读红点复用 IM 的全局未读数接口（IM-010），与 Web 顶栏同一数据源。
import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useApp } from './store';

const TABS = [
  { to: '/', ico: '🔍', label: '广场' },
  { to: '/publish', ico: '➕', label: '发布' },
  { to: '/messages', ico: '💬', label: '消息', badge: true },
  { to: '/profile', ico: '👤', label: '我的' },
] as const;

export default function TabBar() {
  const { client, hasToken } = useApp();
  const { pathname } = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!hasToken) {
      setUnread(0);
      return;
    }
    let alive = true;
    const load = () =>
      client
        .imUnreadCount()
        .then((r) => alive && setUnread(r.unread))
        .catch(() => {
          /* 未读数拿不到不该影响导航可用 */
        });
    void load();
    const timer = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [client, hasToken, pathname]);

  return (
    <nav className="tabbar" aria-label="主导航">
      {TABS.map((t) => {
        const active = t.to === '/' ? pathname === '/' : pathname.startsWith(t.to);
        return (
          <Link key={t.to} to={t.to} className={`tab${active ? ' active' : ''}`}
                aria-current={active ? 'page' : undefined}>
            <span className="ico" aria-hidden="true">{t.ico}</span>
            <span>{t.label}</span>
            {'badge' in t && unread > 0 && (
              <span className="dot" aria-label={`${unread} 条未读`}>
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
