// MOB-040~042 移动端与 PWA 验证（21 号 spec）。
//
// 这里能测的是**结构性约束**：产物里有 manifest 与 SW、SW 不缓存 API、
// 底部 Tab 渲染且带未读红点、安装提示可关闭且记住选择。
// 真实视口渲染需要浏览器环境，由人工/E2E 覆盖，不在此假装验证。
import { PlatformClient } from '@platform/core';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { dismissInstall, isInstallDismissed } from './pwa';
import { AppProvider } from './store';
// 用 Vite 的 ?raw 读静态产物，避免测试依赖 node 类型
import indexHtml from '../index.html?raw';
import manifestRaw from '../public/manifest.webmanifest?raw';
import swSource from '../public/sw.js?raw';
// vitest 默认关闭 CSS 处理，直接 import '*.css?raw' 会得到空串；
// import.meta.glob 显式带 query 才能拿到真实文本
const cssSource = Object.values(
  import.meta.glob('./styles.css', { query: '?raw', import: 'default', eager: true }),
)[0] as string;

function clientWith(unread: number): PlatformClient {
  const fetchImpl = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    text: async () => {
      if (String(url).includes('/conversations/unread-count')) return JSON.stringify({ unread });
      if (String(url).includes('/tasks')) return JSON.stringify([]);
      return JSON.stringify(null);
    },
  })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('PWA 静态产物（MOB-010/011）', () => {
  it('manifest 声明 standalone、主题色与 maskable 图标', () => {
    const manifest = JSON.parse(manifestRaw);
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.theme_color).toMatch(/^#/);
    const purposes = manifest.icons.map((i: { purpose: string }) => i.purpose);
    expect(purposes).toContain('maskable'); // 少了它，安卓自适应图标会被裁掉一圈
  });

  it('index.html 链接 manifest 且 viewport 带 viewport-fit=cover', () => {
    const html = indexHtml;
    expect(html).toContain('rel="manifest"');
    expect(html).toContain('viewport-fit=cover'); // 没有它 safe-area-inset 恒为 0
    expect(html).toContain('name="theme-color"');
  });

  it('Service Worker 绝不缓存 /api——资金与状态数据不能读到陈旧值', () => {
    const sw = swSource;
    expect(sw).toContain("url.pathname.startsWith('/api/')");
    // 预缓存清单里不得出现任何 API 路径
    const precache = sw.slice(sw.indexOf('const PRECACHE'), sw.indexOf('self.addEventListener'));
    expect(precache).not.toContain('/api');
    expect(precache).toContain('OFFLINE_URL');
    expect(sw).toContain("OFFLINE_URL = '/offline.html'"); // MOB-012 离线兜底页
  });

  it('SW 支持 SKIP_WAITING，页面确认后能立刻换新版本（MOB-013）', () => {
    expect(swSource).toContain('SKIP_WAITING');
  });
});

describe('移动端样式约束（MOB-001/003）', () => {
  const css = cssSource;

  it('输入框 ≥16px，防 iOS 聚焦时整页缩放', () => {
    expect(css).toMatch(/input, textarea, select \{ font-size: 16px; \}/);
  });

  it('触控目标 ≥44px', () => {
    expect(css).toContain('min-height: 44px');
  });

  it('底部 Tab 适配手势条安全区', () => {
    expect(css).toContain('env(safe-area-inset-bottom)');
  });

  it('窄屏下表格横向滚动而不是撑破页面', () => {
    expect(css).toContain('.table-wrap { overflow-x: auto');
  });
});

describe('底部 Tab（MOB-002）', () => {
  beforeEach(() => localStorage.clear());

  it('渲染四个主入口', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppProvider client={clientWith(0)}>
          <App />
        </AppProvider>
      </MemoryRouter>,
    );
    const tabbar = await screen.findByLabelText('主导航');
    for (const label of ['广场', '发布', '消息', '我的']) {
      expect(tabbar.textContent).toContain(label);
    }
  });

  it('有未读时消息 Tab 显示红点数字', async () => {
    localStorage.setItem('token', 'tok'); // 未登录时不拉未读数，先put上登录态
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppProvider client={clientWith(7)}>
          <App />
        </AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByLabelText('7 条未读')).toBeDefined());
  });
});

describe('安装引导记忆（MOB-014）', () => {
  beforeEach(() => localStorage.clear());

  it('关闭后记住选择，不再反复骚扰', () => {
    expect(isInstallDismissed()).toBe(false);
    dismissInstall();
    expect(isInstallDismissed()).toBe(true);
  });
});
