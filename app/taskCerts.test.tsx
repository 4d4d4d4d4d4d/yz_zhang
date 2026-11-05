// SCN-294b（407 号 spec，V434）App 发单人按这一单加选资质：类目列了可加的才出；点选后发单带上；详情写明。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { useState } from 'react';
import { TaskCertsNote, TaskCertsPicker } from './taskCerts';
import { PublishScreen } from './App';

const CATS = [
  { id: 1, name: '展台搭建', required_cert: '', optional_certs: ['高处作业操作证', '低压电工作业操作证'] },
  { id: 3, name: '跑腿', required_cert: '' },
];

function makeClient(cats: unknown = CATS): PlatformClient {
  const fetchImpl = (async () => ({ ok: true, status: 200, text: async () => JSON.stringify(cats) })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function Harness({ category, seen, initial = [] }: { category: string; seen: string[][]; initial?: string[] }) {
  const [v, setV] = useState<string[]>(initial);
  return <TaskCertsPicker client={makeClient()} category={category} value={v} onChange={(x) => { seen.push(x); setV(x); }} />;
}

describe('SCN-294b App 加选资质（407 号 spec）', () => {
  it('类目列了可加的才出；点选与取消', async () => {
    const seen: string[][] = [];
    render(<Harness category="展台搭建" seen={seen} />);
    await screen.findByLabelText('这一单另外要的资质');
    fireEvent.press(screen.getByLabelText('加选资质：高处作业操作证'));
    expect(seen[seen.length - 1]).toEqual(['高处作业操作证']);
    fireEvent.press(screen.getByLabelText('加选资质：高处作业操作证'));
    expect(seen[seen.length - 1]).toEqual([]);
  });

  it('没有可加的类目不画；换到这样的类目时清掉上一个类目的勾选', async () => {
    const seen: string[][] = [];
    render(<Harness category="跑腿" seen={seen} initial={['高处作业操作证']} />);
    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    expect(seen[seen.length - 1]).toEqual([]);
    expect(screen.queryByLabelText('这一单另外要的资质')).toBeNull();
  });

  it('类目列表畸形时不画也不崩', async () => {
    const seen: string[][] = [];
    render(<TaskCertsPicker client={makeClient({ oops: 1 })} category="展台搭建" value={[]} onChange={(x) => seen.push(x)} />);
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(screen.queryByLabelText('这一单另外要的资质')).toBeNull();
  });

  it('详情写明这一单另外要什么证；没加不画', () => {
    render(<TaskCertsNote task={{ task_certs: ['民用无人机操控员执照'] }} />);
    expect(screen.getByLabelText('这一单另外要的资质').props.children.join('')).toContain('「民用无人机操控员执照」');
  });
});

describe('SCN-294b/d App 发布页（407 / 408 号 spec）', () => {
  it('勾了加选资质：画像草稿与发单请求都带上', async () => {
    const calls: Array<{ method: string; path: string; body: Record<string, unknown> | null }> = [];
    const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      const body = path === '/categories' ? CATS : method === 'POST' && path === '/tasks' ? { id: 9, title: 'x', status: 'published' } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    const done = jest.fn();
    render(<PublishScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} onDone={done} category="展台搭建" />);
    fireEvent.press(await screen.findByLabelText('加选资质：高处作业操作证'));
    await waitFor(() => expect(calls.some((c) => c.path === '/profiles/task-draft'
      && JSON.stringify(c.body?.task_certs) === JSON.stringify(['高处作业操作证']))).toBe(true), { timeout: 3000 });
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '展台背板');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body!.task_certs).toEqual(['高处作业操作证']);
  });
});
