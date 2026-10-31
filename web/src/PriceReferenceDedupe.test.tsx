// KB-064（266 号 spec）发布页「查参考价」：一位发布方占了大半样本时，写明按发布方去重后的中位价；不集中时照旧。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '店主', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };

function open(ref: unknown) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = p === '/users/me' ? ME : p === '/categories' ? [{ name: '跑腿', required_cert: '' }]
      : p === '/cities' ? [{ id: 1, name: '上海' }] : p === '/knowledge/price-reference' ? ref : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/publish?title=%E5%B8%AE%E5%BF%99&category=%E8%B7%91%E8%85%BF&city=%E4%B8%8A%E6%B5%B7']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

const BASE = { sample_size: 7, p50_cents: 5000, min_cents: 5000, max_cents: 22000, publishers: 4, p50_by_publisher_cents: 19000 };

describe('KB-064 参考价按发布方去重', () => {
  it('集中时写明去重后的中位价', async () => {
    open({ ...BASE, top_publisher_share: 0.571, concentrated: true,
      note: '这 7 单里有 4 单来自同一位发布方；按发布方去重后，4 位发布方的中位价是 ¥190.00，更能代表行情' });
    await screen.findByDisplayValue('帮忙');
    fireEvent.click(screen.getByText('查参考价'));
    const line = await screen.findByText(/同类闭环任务 7 单/);
    expect(line.textContent).toContain('4 位发布方的中位价是 ¥190.00');
  });

  it('不集中时照旧只写原来那句', async () => {
    open({ ...BASE, top_publisher_share: 0.3, concentrated: false, note: '' });
    await screen.findByDisplayValue('帮忙');
    fireEvent.click(screen.getByText('查参考价'));
    const line = await screen.findByText(/同类闭环任务 7 单/);
    expect(line.textContent).not.toContain('去重');
    expect(line.textContent?.trim().endsWith('）')).toBe(true);
  });
});
