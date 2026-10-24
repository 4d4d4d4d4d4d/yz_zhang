// SCN-166（297 号 spec）App 上的交付文件：先看预览，原图锁着时说几张、放款后提示去网页版下载。
import { render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { DeliverablesList } from './deliverables';

function client(list: unknown[]) {
  const fetchImpl = (async () => ({ ok: true, status: 200, text: async () => JSON.stringify(list) })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const P = { id: 8, kind: 'preview', created_at: '2026-10-24T00:00:00Z', locked: false, url: '/api/v1/files/abc' };
const O = { id: 9, kind: 'original', created_at: '2026-10-24T00:00:00Z', locked: true, url: null };

describe('SCN-166 App 交付文件', () => {
  it('放款前：预览可看，原图说锁着', async () => {
    render(<DeliverablesList client={client([P, O])} contractId={3} baseUrl="https://x" />);
    expect((await screen.findByLabelText('预览')).props.source).toEqual({ uri: 'https://x/api/v1/files/abc' });
    expect(screen.getByText('原图 1 张：验收放款后可以下载')).toBeTruthy();
    expect(screen.queryByText(/已可下载/)).toBeNull();
  });

  it('放款后：提示原图已可下载', async () => {
    render(<DeliverablesList client={client([P, { ...O, locked: false, url: '/api/v1/contracts/3/deliverables/9/file' }])} contractId={3} />);
    expect(await screen.findByText('原图 1 张已可下载：请在网页版下载')).toBeTruthy();
    expect(screen.queryByText(/验收放款后可以下载/)).toBeNull();
  });

  it('没有交付文件时不出这一块', async () => {
    const c = client([]);
    const spy = jest.spyOn(c, 'contractDeliverables');
    render(<DeliverablesList client={c} contractId={4} />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith(4));
    expect(screen.queryByLabelText('交付文件')).toBeNull();
  });
});
