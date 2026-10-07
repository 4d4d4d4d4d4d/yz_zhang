import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, it, expect, vi } from 'vitest';
import { Discover, EditSpace } from './Spaces';
const { discoverSpaces, ownSpace, saveSpace } = vi.hoisted(() => ({ discoverSpaces: vi.fn(), ownSpace: vi.fn(), saveSpace: vi.fn() }));
vi.mock('../store', () => { const client = { discoverSpaces, ownSpace, saveSpace }; return { useApp: () => ({ hasToken: true, client }) }; });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const draft = { user_id: 9, nickname: '林', revision: 0, published: false, profile_public: true, headline: '', introduction: '', theme: 'clay', items: [] };
it('shows true empty discovery without fictional members', async () => {
  discoverSpaces.mockResolvedValue({ items: [], next_cursor: null });
  render(<MemoryRouter><Discover /></MemoryRouter>);
  await screen.findByText('第一扇窗口，等你打开');
  expect(screen.getByRole('link', { name: /布置我的空间/ }).getAttribute('href')).toBe('/space/edit');
});
it('failed discovery is not presented as an empty community', async () => {
  discoverSpaces.mockRejectedValue(new Error('offline'));
  render(<MemoryRouter><Discover /></MemoryRouter>);
  await screen.findByRole('alert');
  expect(screen.queryByText('第一扇窗口，等你打开')).toBeNull();
});
it('keeps publication opt-in and only confirms a server accepted save', async () => {
  ownSpace.mockResolvedValue(draft); saveSpace.mockResolvedValue({ ...draft, headline: '机器人设计', revision: 1 });
  render(<MemoryRouter><EditSpace /></MemoryRouter>);
  const headline = await screen.findByLabelText('一句话，让人认识你');
  expect((screen.getByLabelText('公开空间，让别人发现我') as HTMLInputElement).checked).toBe(false);
  fireEvent.change(headline, { target: { value: '机器人设计' } });
  fireEvent.click(screen.getByRole('button', { name: '保存空间' }));
  await screen.findByText('已保存，仅你可见。');
  expect(saveSpace).toHaveBeenCalledWith(expect.objectContaining({ revision: 0, published: false, headline: '机器人设计' }));
});
it('preserves edits when saving fails', async () => {
  ownSpace.mockResolvedValue(draft); saveSpace.mockRejectedValue(new Error('conflict'));
  render(<MemoryRouter><EditSpace /></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText('一句话，让人认识你'), { target: { value: '不要丢失' } });
  fireEvent.click(screen.getByRole('button', { name: '保存空间' }));
  await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  expect((screen.getByLabelText('一句话，让人认识你') as HTMLInputElement).value).toBe('不要丢失');
  expect(screen.queryByText('已保存，仅你可见。')).toBeNull();
});
