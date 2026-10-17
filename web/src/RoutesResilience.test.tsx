// APP-091 / APP-092 每一页都不白屏（183 号 spec）。
// 每个路由 × 四种畸形响应（{}、null、[]、字符串）：顶部导航必须还在。首次跑时 140 个组合里 91 个整页白屏
// （约 30 个页面组件拿到非数组就 .map 崩掉）；按路由加错误边界后，坏的那一页换成说明卡，导航与其他页不受影响。
// 新加的页面要加进 ROUTES（与 App.tsx 的路由表对照）。
// V213（APP-093）再收紧：连整页兜底卡片也不许出现（那时还有 32 个页面组件会落到兜底）。
import { PlatformClient } from '@platform/core';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'fs';
import { join } from 'path';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (admin: boolean) => ({ id: 1, phone: '138', nickname: '探针用户', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: admin, admin_roles: [], credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r' });
const ROUTES = ['/', '/admin', '/ask', '/chain', '/circles', '/community', '/cooperate', '/developer', '/gig', '/influence',
  '/messages', '/missions', '/notebook', '/notifications', '/opc', '/opportunities', '/packs', '/people/1', '/people/1/follows',
  '/profile', '/publish', '/records', '/rewards', '/sandbox', '/search', '/space/edit', '/support', '/tasks/7/decompose',
  '/teams', '/teams/join/abc', '/ventures', '/verify', '/wallet', '/workbench', '/xapp'];
describe('APP-091 Web 每一页：响应畸形时都不白屏（导航还在）', () => {
  for (const [label, body] of [['{}', {}], ['null', null], ['[]', []], ['x', 'x']] as Array<[string, unknown]>)
    for (const route of ROUTES)
      it(`${route} · 响应 ${label}`, async () => {
        localStorage.setItem('token', 'tok');
        const fetchImpl = vi.fn(async (url: string) => {
          const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
          const out = p === '/users/me' ? ME(route === '/admin') : body;
          return { ok: true, status: 200, text: async () => JSON.stringify(out) };
        }) as unknown as typeof fetch;
        const { container } = render(<MemoryRouter initialEntries={[route]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
        await new Promise((r) => setTimeout(r, 60));
        expect(container.textContent).toContain('工作台');   // 顶部导航还在：没有白屏
        // APP-093（V213）：也不许落到整页兜底——列表响应在 SDK 里收成空表，对象响应不像样时只那一块说明原因
        expect(container.querySelector('[aria-label="这一页没加载出来"]')).toBeNull();
      });

  it('路由表里的每一页都在探针里（新加的页面别漏）', () => {
    const src = readFileSync(join(__dirname, 'App.tsx'), 'utf8');
    const declared = [...src.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1])
      .filter((p) => p !== '/login' && p !== '/tasks/:id')        // 登录页不调接口；任务详情由 DetailResilience 覆盖
      .map((p) => p.replace(':id', p.startsWith('/people') ? '1' : '7').replace(':token', 'abc'));
    expect(declared.filter((p) => !ROUTES.includes(p))).toEqual([]);
  });
});
