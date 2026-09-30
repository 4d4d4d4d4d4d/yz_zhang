// Web 端冒烟测试：路由渲染 + 广场数据展示 + 登录守卫
import { PlatformClient } from '@platform/core';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

function clientWith(tasks: unknown[]): PlatformClient {
  const fetchImpl = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    text: async () => {
      if (String(url).includes('/tasks')) return JSON.stringify(tasks);
      return JSON.stringify(null);
    },
  })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => null, fetchImpl });
}

const SAMPLE_TASK = {
  id: 1, creator_id: 2, executor_id: null, parent_id: null, depends_on: [],
  title: '周末大扫除', description: '', category: '保洁', task_type: 'service',
  required_skills: [], budget_cents: 20000, pricing: 'fixed', is_remote: false,
  city: '上海', lat: 31.2, lng: 121.4, address_hint: '静安寺商圈', address_exact: '',
  status: 'published', deadline: null, reject_count: 0, created_at: '2026-07-02T00:00:00',
  distance_m: null,
};

function renderAt(path: string, tasks: unknown[] = []) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProvider client={clientWith(tasks)}>
        <App />
      </AppProvider>
    </MemoryRouter>,
  );
}

describe('App', () => {
  it('广场渲染任务卡：标题/价格/状态/脱敏地址', async () => {
    renderAt('/', [SAMPLE_TASK]);
    await waitFor(() => expect(screen.getByText('周末大扫除')).toBeTruthy());
    expect(screen.getByText('¥200.00')).toBeTruthy();
    expect(screen.getByText('招募中')).toBeTruthy();
    expect(screen.getByText(/静安寺商圈/)).toBeTruthy();
  });

  it('广场为空时提示引导发布', async () => {
    renderAt('/', []);
    await waitFor(() => expect(screen.getByText(/暂无任务/)).toBeTruthy());
  });

  it('未登录访问钱包被重定向到登录页', async () => {
    localStorage.removeItem('token');
    renderAt('/wallet');
    await waitFor(() => expect(screen.getByPlaceholderText('13800000000')).toBeTruthy());
  });

  it('导航包含核心入口', async () => {
    renderAt('/');
    // 顶栏与底部 Tab 会有同名入口（如「消息」），因此按区域取而不是全局取
    const topNav = document.querySelector('nav.nav') as HTMLElement;
    for (const label of ['任务广场', '发布任务', '消息', '钱包', '客服']) {
      expect(topNav.textContent).toContain(label);
    }
  });
});
