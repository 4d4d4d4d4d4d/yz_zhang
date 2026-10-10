import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, it, expect, vi } from 'vitest';
import { Discover, EditSpace, PublicSpace } from './Spaces';
const { discoverSpaces, ownSpace, saveSpace, personalSpace, followStats, followUser, unfollowUser, openDirect, navigate } = vi.hoisted(() => ({ discoverSpaces: vi.fn(), ownSpace: vi.fn(), saveSpace: vi.fn(), personalSpace: vi.fn(), followStats: vi.fn(), followUser: vi.fn(), unfollowUser: vi.fn(), openDirect: vi.fn(), navigate: vi.fn() }));
vi.mock('../store', () => { const client = { discoverSpaces, ownSpace, saveSpace, personalSpace, followStats, followUser, unfollowUser, openDirect }; return { useApp: () => ({ hasToken: hasTokenValue, client, me: { id: 1 } }) }; });
vi.mock('react-router-dom', async () => ({ ...(await vi.importActual<object>('react-router-dom')), useNavigate: () => navigate }));
// 第三条用例要验「游客被送去登录」，所以 hasToken 要能改
let hasTokenValue = true;
const person = { user_id: 9, nickname: '林', headline: '做结构设计', theme: 'clay', kind: 'person', items_count: 0, accepting_orders: true, introduction: '' };
afterEach(() => { cleanup(); vi.resetAllMocks(); hasTokenValue = true; });
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

// CNT-022 关注：状态从服务端读，关注与取消是两个不同的动作。
//
// 改造前服务端是一个 toggle，而客户端读不到「我是否已关注」——
// 于是按钮只能猜，猜错就把「想关注」变成了「取消关注」。
it('reads follow state from the server instead of guessing it', async () => {
  personalSpace.mockResolvedValue({ ...person, items: [] });
    // 两个键故意取相反的真值：他关注了 0 个人，而我已经关注了他。
  // 读成 `following` 会得到 false，画出「关注」——而真相是「已关注」。
  followStats.mockResolvedValue({ followers: 3, following: 0, viewer_following: true });
  render(<MemoryRouter initialEntries={['/people/9']}>
    <Routes><Route path="/people/:id" element={<PublicSpace />} /></Routes>
  </MemoryRouter>);
  // `following` 是「他关注了多少人」的计数，不是我的状态——
  // 读错这个键，按钮会随别人关注了几个人而变
  await screen.findByRole('button', { name: '已关注' });
  expect(screen.getByText('3 人关注')).toBeTruthy();
});

it('an already-followed space unfollows, and a new one follows (no toggle guessing)', async () => {
  personalSpace.mockResolvedValue({ ...person, items: [] });
  followStats.mockResolvedValue({ followers: 3, following: 0, viewer_following: true });
  unfollowUser.mockResolvedValue({ following: false });
  render(<MemoryRouter initialEntries={['/people/9']}>
    <Routes><Route path="/people/:id" element={<PublicSpace />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: '已关注' }));
  await screen.findByRole('button', { name: '关注' });
  expect(unfollowUser).toHaveBeenCalledWith(9);
  expect(followUser).not.toHaveBeenCalled();
  expect(screen.getByText('2 人关注')).toBeTruthy();
});

it('a visitor who is not signed in is sent to login rather than given a dead button', async () => {
  hasTokenValue = false;
  personalSpace.mockResolvedValue({ ...person, items: [] });
  // 匿名时 viewer_following 是 null（「没登录所以不知道」），不是 false
  followStats.mockResolvedValue({ followers: 0, following: 0, viewer_following: null });
  render(<MemoryRouter initialEntries={['/people/9']}>
    <Routes><Route path="/people/:id" element={<PublicSpace />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: '关注' }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith('/login?next=%2Fpeople%2F9'));
  expect(followUser).not.toHaveBeenCalled();
});
