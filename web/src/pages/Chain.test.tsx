import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import Chain from './Chain';
afterEach(() => vi.unstubAllGlobals());
it('never enables wallet transactions when deployment is absent', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
  render(<MemoryRouter><Chain /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('链上环境尚未配置'));
  expect((screen.getByRole('button', { name: '连接钱包' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: '发起链上协作' }) as HTMLButtonElement).disabled).toBe(true);
});
