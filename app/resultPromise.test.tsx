// SCN-185（311 号 spec）App 上发单人看报名列表：留言里承诺了结果的标出来（不拦）；没承诺的照旧。
import { render, screen } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

const TASK = { id: 7, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '改简历', description: '',
  category: '求职辅导', task_type: 'simple', required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: true, city: '', lat: null, lng: null, address_hint: '', address_exact: '', deadline: null,
  reject_count: 0, created_at: '2026-10-16T00:00:00Z', status: 'published' } as unknown as Task;
const FLAG = '这条报名承诺了结果（保 offer、包过之类）：录用、录取由对方机构决定，谁也保证不了，选人时多留个心';

describe('SCN-185 App 报名列表里的结果承诺', () => {
  it('承诺了的标出来，没承诺的不标', async () => {
    const apps = [
      { id: 21, applicant_id: 5, nickname: '甲', credit_score: 100, rating_avg: 0, bid_cents: 20000, message: '包就业', status: 'pending', promise_flag: FLAG },
      { id: 22, applicant_id: 6, nickname: '乙', credit_score: 100, rating_avg: 0, bid_cents: 20000, message: '改两轮', status: 'pending' },
    ];
    const fetchImpl = (async (url: string) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      return { ok: true, status: 200, text: async () => JSON.stringify(path === '/tasks/7/applications' ? apps : []) };
    }) as unknown as typeof fetch;
    render(<TaskDetailScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}
                             me={{ id: 1, nickname: 'x' } as unknown as Me} task={TASK}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
    expect(await screen.findByText(`⚠ ${FLAG}`)).toBeTruthy();
    expect(screen.getAllByText(/这条报名承诺了结果/)).toHaveLength(1);
  });
});
