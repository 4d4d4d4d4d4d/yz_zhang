// OUT-052（444 号 spec）网页发单页选「按结果计价」：关键词变成平台判定指标；写上限带 bonus_cents，写分档带 bonus_tiers；没填完的当场说清。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '店主', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
type Call = { method: string; path: string; body?: unknown };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME : p === '/categories' ? [{ name: '软件开发', required_cert: '' }]
      : p === '/cities' ? [{ id: 1, name: '上海' }] : method === 'POST' && p === '/tasks' ? { id: 50, title: '写接口文档', status: 'published', slots: [] } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/publish?title=%E5%86%99%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3&category=%E8%BD%AF%E4%BB%B6%E5%BC%80%E5%8F%91&city=%E4%B8%8A%E6%B5%B7']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

async function chooseOutcome() {
  await screen.findByDisplayValue('写接口文档');
  fireEvent.change(screen.getByDisplayValue('一口价'), { target: { value: 'outcome' } });
  fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
}
const posted = (calls: Call[]) => calls.find((c) => c.method === 'POST' && c.path === '/tasks')?.body as Record<string, unknown> | undefined;

describe('OUT-052 网页发单页按结果计价', () => {
  it('只写上限：关键词变成平台判定指标，带 bonus_cents、pricing=outcome', async () => {
    const calls: Call[] = [];
    open(calls);
    await chooseOutcome();
    const box = screen.getByLabelText('按结果计价');
    fireEvent.change(box.querySelector('input')!, { target: { value: '已自测，已附文档' } });
    fireEvent.change(screen.getByLabelText(/全部达标加付/), { target: { value: '50' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(posted(calls)).toMatchObject({ pricing: 'outcome', bonus_cents: 5000, acceptance_criteria: [
      { text: '交付说明写明「已自测」', kind: 'auto', check: { op: 'contains', value: '已自测' } },
      { text: '交付说明写明「已附文档」', kind: 'auto', check: { op: 'contains', value: '已附文档' } }] }));
    expect(posted(calls)).not.toHaveProperty('bonus_tiers');
  });

  it('写了分档：带 bonus_tiers、不带 bonus_cents；分档只填一半的当场说清、不发请求', async () => {
    const calls: Call[] = [];
    open(calls);
    await chooseOutcome();
    const box = screen.getByLabelText('按结果计价');
    fireEvent.change(box.querySelector('input')!, { target: { value: '已自测，已部署' } });
    fireEvent.click(screen.getByText('＋加一档'));
    fireEvent.change(screen.getByLabelText('第1档通过几条'), { target: { value: '1' } });
    fireEvent.submit(box.closest('form')!);
    expect(await screen.findByText('每一档都要写「通过几条」和「加付多少元」')).toBeTruthy();
    expect(posted(calls)).toBeUndefined();
    fireEvent.change(screen.getByLabelText('第1档加付'), { target: { value: '20' } });
    fireEvent.click(screen.getByText('＋加一档'));
    fireEvent.change(screen.getByLabelText('第2档通过几条'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('第2档加付'), { target: { value: '90' } });
    fireEvent.submit(box.closest('form')!);
    await waitFor(() => expect(posted(calls)).toMatchObject({ pricing: 'outcome',
      bonus_tiers: [{ min_passed: 1, bonus_cents: 2000 }, { min_passed: 2, bonus_cents: 9000 }] }));
    expect(posted(calls)).not.toHaveProperty('bonus_cents');
  });

  it('一口价的照旧不带这些字段', async () => {
    const calls: Call[] = [];
    open(calls);
    await screen.findByDisplayValue('写接口文档');
    expect(screen.queryByLabelText('按结果计价')).toBeNull();
    fireEvent.change(screen.getByDisplayValue('— 请选择 —'), { target: { value: 'assign' } });
    fireEvent.submit(screen.getByDisplayValue('一口价').closest('form')!);
    await waitFor(() => expect(posted(calls)).toBeTruthy());
    expect(posted(calls)).not.toHaveProperty('acceptance_criteria');
    expect(posted(calls)).not.toHaveProperty('bonus_cents');
  });
});
