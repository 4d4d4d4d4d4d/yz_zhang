/* MOB-011/012 Service Worker
 *
 * 缓存策略只有两条，且第二条是硬红线：
 *   1. 应用外壳（HTML/JS/CSS/图标）：stale-while-revalidate —— 秒开且后台更新。
 *   2. **/api/ 一律不缓存，也不兜底** —— 任务状态、合约状态、钱包余额一旦
 *      读到陈旧值，用户会基于错误信息做出付钱/放款决定。宁可报错，不可撒谎。
 */
const VERSION = 'v3';
const SHELL_CACHE = `shell-${VERSION}`;
const OFFLINE_URL = '/offline.html';

const PRECACHE = ['/', '/index.html', OFFLINE_URL, '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(PRECACHE)),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// MOB-013：页面确认后立刻换新版本，避免旧外壳打新接口
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

function isApiRequest(url) {
  return url.pathname.startsWith('/api/');
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // 红线：API 直连网络，不读缓存、不写缓存、失败就失败
  if (isApiRequest(url)) return;

  // 导航请求：网络优先（拿最新外壳），断网落离线页
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(SHELL_CACHE).then((c) => c.put('/index.html', copy));
          return resp;
        })
        .catch(() => caches.match('/index.html').then((r) => r || caches.match(OFFLINE_URL))),
    );
    return;
  }

  // 静态资源：stale-while-revalidate
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((resp) => {
          if (resp.ok) {
            const copy = resp.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(request, copy));
          }
          return resp;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});
