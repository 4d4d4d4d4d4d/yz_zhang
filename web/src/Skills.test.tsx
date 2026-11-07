// SKL-100 技能概念表（135 号 spec）：资料页写技能时说清会按什么匹配；后台维护概念。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SkillConceptsAdmin } from './AdminSkills';
import { SkillHints, SkillSuggestions } from './Profiles';
import { AppProvider } from './store';

type Call = { method: string; path: string; query: string; body?: unknown };
function mount(node: React.ReactNode, routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const [p, query = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, query, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}>{node}</AppProvider></MemoryRouter>);
  return calls;
}

describe('SKL-106 技能怎么匹配', () => {
  it('别名写清按哪个规范名匹配，认不出的如实说', async () => {
    const calls = mount(<SkillHints skills={['VI设计', '剪纸', '保洁']} />, { '/skills/normalize': { items: [
      { skill: 'VI设计', canonical: '品牌设计', known: true }, { skill: '剪纸', canonical: '剪纸', known: false },
      { skill: '保洁', canonical: '保洁', known: true }] } });
    const p = await screen.findByLabelText('技能怎么匹配', {}, { timeout: 3000 });
    expect(p.textContent).toBe('「VI设计」按「品牌设计」匹配；「剪纸」平台还不认识，只按原样匹配');
    expect(calls[0].query).toBe(`skills=${encodeURIComponent('VI设计,剪纸,保洁')}`);
  });
});

describe('SKL-101 后台技能概念表', () => {
  it('查、改、保存', async () => {
    const calls = mount(<SkillConceptsAdmin />, {
      '/admin/skill-concepts': { effective: [{ name: '品牌设计', aliases: ['VI设计', 'logo设计'] }, { name: '保洁', aliases: ['打扫'] }], overrides: [] },
      'POST /admin/skill-concepts': { id: 1, name: '品牌设计', aliases: ['VI设计', 'logo设计', '品牌VI'], status: 'active', updated_by: 1, updated_at: '' },
    });
    fireEvent.change(await screen.findByLabelText('查概念'), { target: { value: 'logo' } });
    const box = screen.getByLabelText('技能概念表');
    await waitFor(() => expect(box.textContent).toContain('品牌设计'));
    expect(box.textContent).not.toContain('打扫');
    fireEvent.click(screen.getByRole('button', { name: '改' }));
    fireEvent.change(screen.getByLabelText('别名'), { target: { value: 'VI设计、logo设计、品牌VI' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await screen.findByText('已保存「品牌设计」');
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ name: '品牌设计', aliases: ['VI设计', 'logo设计', '品牌VI'] });
  });
});

describe('SKL-106 平台认得的技能', () => {
  it('列出没写过的规范名，点一下加进去', async () => {
    const onAdd = vi.fn();
    mount(<SkillSuggestions current={['保洁']} onAdd={onAdd} />, { '/skills/concepts': { items: [{ name: '保洁', aliases: [] }, { name: '品牌设计', aliases: [] }] } });
    const p = await screen.findByLabelText('平台认得的技能');
    expect(p.textContent).toBe('平台认得的技能：品牌设计');
    fireEvent.click(screen.getByRole('button', { name: '品牌设计' }));
    expect(onAdd).toHaveBeenCalledWith('品牌设计');
  });
});
