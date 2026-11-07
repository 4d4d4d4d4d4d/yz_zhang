// TASK-022d（390 号 spec）：任务详情页里的交付预览原来没拿到服务端地址，预览图是相对路径，真机上加载不出来。
import { render, screen } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

function makeClient(routes: Record<string, unknown>) {
  const fetchImpl = (async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TASK = { id: 70, creator_id: 9, executor_id: 2, parent_id: null, depends_on: [], title: '拍主图',
  description: '', category: '商品拍摄', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed',
  ip_assignment: 'assign', bonus_cents: 0, is_remote: true, city: '', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'in_progress', deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z' } as unknown as Task;
const CONTRACT = { id: 31, task_id: 70, requester_id: 9, executor_id: 2, amount_cents: 20000, status: 'funded', frozen: false,
  released_cents: 0, milestones: [] };

describe('TASK-022d 详情页的图片地址', () => {
  it('交付预览与进度照片都拼上服务端地址（测试环境是 http://localhost:8000）', async () => {
    const client = makeClient({
      '/contracts/by-task/70': CONTRACT,
      '/contracts/31/deliverables': [{ id: 8, kind: 'preview', created_at: '2026-10-24T00:00:00Z', locked: false, url: '/api/v1/files/abc' }],
      '/tasks/70/progress': [{ id: 1, user_id: 2, kind: 'note', content: '拍好了', images: ['/api/v1/files/p1'], created_at: '2026-11-04T08:00:00Z' }],
    });
    render(<TaskDetailScreen client={client} me={{ id: 9, nickname: '店主' } as never} task={TASK} onBack={() => {}} onChanged={async () => {}} />);
    const preview = await screen.findByLabelText('预览');
    expect(preview.props.source.uri).toMatch(/^https?:\/\/[^/]+\/api\/v1\/files\/abc$/);
    const photo = await screen.findByLabelText('进度照片 1');
    expect(photo.props.source.uri).toMatch(/^https?:\/\/[^/]+\/api\/v1\/files\/p1$/);
  });
});

describe('APP-120 前一步的预览图（394 号 spec）', () => {
  it('项目里的一步：接单人看到的前一步预览图拼上了服务端地址', async () => {
    const step = { ...TASK, id: 71, parent_id: 70, creator_id: 9, executor_id: 2, title: '修图' } as unknown as Task;
    const client = makeClient({
      '/tasks/71/inputs': [{ from_task_id: 70, title: '拍主图', shared_at: '2026-11-04T08:00:00Z', deliveries: [{ content: '原片已传' }],
        previews: [{ id: 5, url: '/api/v1/files/prev1' }, { id: 6, url: 'javascript:alert(1)' }] }],
    });
    render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '修图师' } as never} task={step} onBack={() => {}} onChanged={async () => {}} />);
    const imgs = await screen.findAllByLabelText('前一步的预览图');
    expect(imgs).toHaveLength(1);
    expect(imgs[0].props.source.uri).toMatch(/^https?:\/\/[^/]+\/api\/v1\/files\/prev1$/);
  });
});
