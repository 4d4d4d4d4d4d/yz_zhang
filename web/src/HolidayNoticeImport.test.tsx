// ESCA-072（288 号 spec）后台节假日日历：贴通知原文 → 草稿 → 核对（改按周几、删错的）→ 一次保存。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const BOSS = { id: 1, phone: '138****0001', nickname: '主管', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['super'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
// 工单台没有工单时整块不显示（TicketQueue），给一张
const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };
const LABELS = { funds: '资金（提现、退款、到账）', account: '账号（登录、安全）', general: '一般' };
const NOTICE = '一、元旦：1月1日（周五）放假1天。\n二、劳动节：5月1日（周六）至3日（周一）放假调休，共3天。4月25日（周日）上班。\n三、某节：另行通知。';
type Call = { method: string; url: string; body?: unknown };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const sent = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, url: p, body: sent });
    const body = p === '/users/me' ? BOSS : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/my-categories' ? { categories: [], declared: false, labels: LABELS }
      : p === '/admin/support/holidays/bulk' ? { created: sent.items.slice(1).map((x: object, k: number) => ({ id: 10 + k, ...x })), skipped: [sent.items[0].day] }
      : p === '/admin/admins' ? { admins: [] }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

async function importBox() {
  fireEvent.click(await screen.findByText('看客服状态'));
  return screen.findByLabelText('按通知导入');
}

describe('ESCA-072 按通知导入节假日', () => {
  it('解析出草稿、列出认不出的条目；改调休按周几、删一条后保存的就是核对后的草稿', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await importBox();
    expect((within(box).getByText('解析成草稿') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('通知原文'), { target: { value: NOTICE } });
    fireEvent.change(within(box).getByLabelText('年份'), { target: { value: '2027' } });
    fireEvent.click(within(box).getByText('解析成草稿'));
    expect(within(box).getByTestId('draft-2027-04-25').textContent).toContain('调休上班 劳动节调休上班');
    expect(within(box).getByText(/这几条没认出日期/).textContent).toContain('某节：另行通知。');
    expect((within(box).getByLabelText('2027-04-25 按周几的排班') as HTMLSelectElement).value).toBe('4');
    fireEvent.change(within(box).getByLabelText('2027-04-25 按周几的排班'), { target: { value: '0' } });
    fireEvent.click(within(within(box).getByTestId('draft-2027-05-03')).getByText('删掉'));
    fireEvent.click(within(box).getByText('保存这 4 天'));
    await waitFor(() => expect(calls.find((c) => c.url === '/admin/support/holidays/bulk')?.body).toEqual({ items: [
      { day: '2027-01-01', kind: 'off', label: '元旦', as_weekday: null },
      { day: '2027-04-25', kind: 'workday', label: '劳动节调休上班', as_weekday: 0 },
      { day: '2027-05-01', kind: 'off', label: '劳动节', as_weekday: null },
      { day: '2027-05-02', kind: 'off', label: '劳动节', as_weekday: null },
    ] }));
    expect((await within(box).findByRole('status')).textContent).toBe('已导入 3 天；2027-01-01 已经录过，跳过');
    expect(within(box).queryByTestId('draft-2027-05-01')).toBeNull();
  });

  it('一个日期都没认出时说清要贴什么，不发请求', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await importBox();
    fireEvent.change(within(box).getByLabelText('通知原文'), { target: { value: '明年怎么放假？' } });
    fireEvent.click(within(box).getByText('解析成草稿'));
    expect(within(box).getByText(/没认出任何日期/)).toBeTruthy();
    expect(within(box).queryByText(/保存这/)).toBeNull();
    expect(calls.some((c) => c.url === '/admin/support/holidays/bulk')).toBe(false);
  });
});
