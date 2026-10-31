// APP-090 详情页每一块都扛得住畸形响应（182 号 spec）。
//
// 任务详情页由十几块拼成（合约、变更单、纠纷、上门回报、子任务进度、报名列表……），每块各自请求。
// 以前只有几块写了「响应不像预期时不画」，变更单块、报名列表拿到 {} / null 就把整页带崩——
// 用户看到的是白屏，而不是那一块没出来。这里把每个状态 × 发单人 / 接单人 × 四种畸形响应
// × 合约正常 / 合约也畸形，都渲染一遍：标题必须还在。
import { render, screen } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

const BASE = { id: 7, creator_id: 1, executor_id: 2, parent_id: null, depends_on: [], title: '探针', description: '',
  category: '跑腿', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: 31.2, lng: 121.4, address_hint: '', address_exact: '', deadline: null,
  reject_count: 0, created_at: '2026-10-16T00:00:00Z', visits_planned: 2, visit_checklist: ['a'], days: 2, people_needed: 2,
} as unknown as Task;
const CONTRACT = { id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000, released_cents: 0, fee_bps: 800, terms: '',
  status: 'funded', signed_by_requester: true, signed_by_executor: true, frozen: false, version: 1, deposit_cents: 0,
  deposit_status: 'none', milestones: [{ idx: 1, title: '全部', amount_cents: 20000, status: 'pending' }] };
const STATUSES = ['published', 'matched', 'in_progress', 'pending_acceptance', 'completed', 'disputed'];
const BODIES: Array<[string, unknown]> = [['{}', {}], ['null', null], ['[]', []], ['"x"', 'x']];

describe('APP-090 任务详情页：任何一块的响应畸形都不许把整页带崩', () => {
  for (const goodContract of [true, false]) {
    for (const [label, body] of BODIES) {
      for (const status of STATUSES) {
        for (const me of [1, 2]) {
          it(`响应 ${label} · ${status} · ${me === 1 ? '发单人' : '接单人'} · 合约${goodContract ? '正常' : '也畸形'}`, async () => {
            const fetchImpl = (async (url: string) => {
              const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
              const out = goodContract && path === '/contracts/by-task/7' ? CONTRACT : body;
              return { ok: true, status: 200, text: async () => JSON.stringify(out) };
            }) as unknown as typeof fetch;
            const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
            render(<TaskDetailScreen client={client} me={{ id: me, nickname: 'x' } as unknown as Me}
                                     task={{ ...BASE, status } as Task}
                                     onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
            await new Promise((r) => setTimeout(r, 30));   // 让各块的请求都回来、都画一遍
            expect(screen.getByText('探针')).toBeTruthy();
          });
        }
      }
    }
  }

  const DISPUTE = { id: 11, task_id: 7, status: 'open', reason: '没按时到', initiator_id: 1, respondent_id: 2,
    response_deadline: '2030-01-01T00:00:00Z', created_at: '2026-10-16T00:00:00Z' };
  function renderWith(routes: Record<string, unknown>) {
    const fetchImpl = (async (url: string) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      return { ok: true, status: 200, text: async () => JSON.stringify(path in routes ? routes[path] : []) };
    }) as unknown as typeof fetch;
    render(<TaskDetailScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}
                             me={{ id: 1, nickname: 'x' } as unknown as Me} task={{ ...BASE, status: 'disputed' } as Task}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
  }

  it('纠纷响应不像一条纠纷：不画纠纷块', async () => {
    renderWith({ '/tasks/7/dispute': {}, '/disputes/undefined/statements': [] });
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/纠纷 #/)).toBeNull();
  });

  it('纠纷正常、陈述列表畸形：纠纷块照画，页面不崩', async () => {
    renderWith({ '/tasks/7/dispute': DISPUTE, '/disputes/11/statements': { oops: true } });
    expect(await screen.findByText(/纠纷 #11/)).toBeTruthy();
    expect(screen.getByText('探针')).toBeTruthy();
  });
});
