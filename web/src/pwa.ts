// MOB-010/013/014 PWA 装载：注册 SW、新版本提示、安装引导。
// 这些能力在不支持的环境（含测试用的 jsdom）里必须安静降级，绝不抛错。

type UpdateHandler = () => void;

let deferredInstall: BeforeInstallPromptEvent | null = null;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const DISMISS_KEY = 'pwa-install-dismissed';

export function registerServiceWorker(onUpdate?: UpdateHandler): void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  if (import.meta.env.DEV) return; // 开发环境不注册，避免缓存干扰热更新

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        reg.addEventListener('updatefound', () => {
          const next = reg.installing;
          if (!next) return;
          next.addEventListener('statechange', () => {
            // 已有旧 SW 在控制页面 + 新 SW 装好 = 有新版本可用
            if (next.state === 'installed' && navigator.serviceWorker.controller) {
              onUpdate?.();
            }
          });
        });
      })
      .catch(() => {
        /* 注册失败不影响正常使用 */
      });
  });
}

export function applyUpdate(): void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  navigator.serviceWorker.getRegistration().then((reg) => {
    reg?.waiting?.postMessage('SKIP_WAITING');
    window.location.reload();
  });
}

export function watchInstallPrompt(onAvailable: () => void): void {
  if (typeof window === 'undefined') return;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); // 阻止浏览器默认横幅，改由我们在合适时机引导
    deferredInstall = e as BeforeInstallPromptEvent;
    if (!isInstallDismissed()) onAvailable();
  });
}

export async function promptInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  if (!deferredInstall) return 'unavailable';
  await deferredInstall.prompt();
  const { outcome } = await deferredInstall.userChoice;
  deferredInstall = null;
  if (outcome === 'dismissed') dismissInstall();
  return outcome;
}

export function isInstallDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false; // 隐私模式下 localStorage 可能直接抛异常
  }
}

export function dismissInstall(): void {
  try {
    localStorage.setItem(DISMISS_KEY, '1'); // MOB-014 记住选择，别反复骚扰
  } catch {
    /* 忽略 */
  }
}
