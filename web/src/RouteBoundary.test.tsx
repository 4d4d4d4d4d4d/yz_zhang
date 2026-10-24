// APP-092 Web 页面错误边界（183 号 spec）：一页渲染出错只坏这一页，导航还在；换一页自动复位。
import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PlatformClient } from '@platform/core';
import RouteBoundary, { pageKey } from './RouteBoundary';
import { AppProvider } from './store';

function Boom(): JSX.Element { throw new TypeError('rows.map is not a function'); }

type Call = { path: string; body?: unknown };
const calls: Call[] = [];
function wrap(entries: string[]) {
  const fetchImpl = vi.fn(async (url: string, init?: { body?: string }) => {
    calls.push({ path: String(url).replace(/^.*\/api\/v1/, ''), body: init?.body ? JSON.parse(init.body) : undefined });
    return { ok: true, status: 201, text: async () => JSON.stringify({ ok: true, recorded: true }) };
  }) as unknown as typeof fetch;
  return (<MemoryRouter initialEntries={entries}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => null, fetchImpl })}>
      <nav><Link to="/ok">去好的那页</Link></nav>
      <RouteBoundary><Routes>
        <Route path="/bad" element={<Boom />} /><Route path="/people/:id" element={<Boom />} /><Route path="/ok" element={<p>好的那页</p>} />
      </Routes></RouteBoundary>
    </AppProvider>
  </MemoryRouter>);
}

describe('APP-092 Web 页面错误边界', () => {
  beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}); });
  afterEach(() => vi.restoreAllMocks());

  it('一页出错：导航在、换成说明卡；只记错误类型；点到别的页正常显示', () => {
    render(wrap(['/bad']));
    expect(screen.getByRole('alert', { name: '这一页没加载出来' })).toBeTruthy();
    expect(screen.getByText('去客服')).toBeTruthy();
    expect(console.error).toHaveBeenCalledWith('page_render_failed', 'TypeError');
    fireEvent.click(screen.getByText('去好的那页'));
    expect(screen.getByText('好的那页')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('APP-094 上报只有页面与错误类型；路径里的 id 与邀请口令不报', async () => {
    calls.length = 0;
    render(wrap(['/people/13800000001']));
    await screen.findByRole('alert');
    await new Promise((r) => setTimeout(r, 10));
    const sent = calls.filter((c) => c.path === '/client-errors');
    expect(sent.map((c) => c.body)).toContainEqual({ platform: 'web', page: '/people/:id', kind: 'TypeError' });
    expect(JSON.stringify(sent)).not.toContain('13800000001');
    expect(pageKey('/teams/join/abc123XYZ')).toBe('/teams/join/:token');
    expect(pageKey('/tasks/42/decompose')).toBe('/tasks/:id/decompose');
  });
});
