// ACC-020 实名核验在 App 上（V125 重写，100 号 spec）。
//
// 原来是一个「一键实名认证（模拟）」按钮，把写死的「测试用户」与证件号
// 110101199001011234 提交给服务端：第一个点的人账号上被记下的真实姓名是
// 「测试用户」，之后每一个点的人都收到 id_already_bound，而那个 onPress
// 没有 try/catch——**点了什么都不会发生**。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { VerifyIdentityBlock } from './App';

function makeClient(
  verify: { status: number; body: unknown },
  calls: Array<{ path: string; body: unknown }> = [],
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ path, body: init?.body ? JSON.parse(init.body) : null });
    return {
      ok: verify.status < 400, status: verify.status,
      text: async () => JSON.stringify(verify.body),
    };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function fill(name: string, id: string) {
  fireEvent.changeText(screen.getByPlaceholderText('真实姓名'), name);
  fireEvent.changeText(screen.getByPlaceholderText('身份证号（15 或 18 位）'), id);
  fireEvent.press(screen.getByText('提交实名认证'));
}

describe('ACC-020 App 实名核验', () => {
  it('提交的是用户填的，不是写死的身份', async () => {
    const calls: Array<{ path: string; body: unknown }> = [];
    const onDone = jest.fn();
    render(<VerifyIdentityBlock
      client={makeClient({ status: 200, body: { is_verified: true, status: 'verified' } }, calls)}
      onDone={onDone} />);
    fill('李四', '11010119900101123X');
    await waitFor(() => expect(screen.getByText('实名认证已通过')).toBeTruthy());
    expect(calls[0].body).toEqual({ real_name: '李四', id_number: '11010119900101123X' });
    expect(JSON.stringify(calls)).not.toContain('110101199001011234');
    expect(onDone).toHaveBeenCalled();
  });

  it('转人工时说「正在人工审核」，不说通过', async () => {
    render(<VerifyIdentityBlock
      client={makeClient({ status: 200, body: { is_verified: false, status: 'manual_review' } })}
      onDone={() => {}} />);
    fill('张三', '110101199001011235');
    await waitFor(() => expect(screen.getByText(/正在人工审核/)).toBeTruthy());
    expect(screen.queryByText('实名认证已通过')).toBeNull();
  });

  it('证件号已被绑定时把服务端的话显示出来——**而不是点了没反应**', async () => {
    render(<VerifyIdentityBlock
      client={makeClient({ status: 409, body: { detail: { code: 'id_already_bound', message: '该证件号已绑定其它账号' } } })}
      onDone={() => {}} />);
    fill('王五', '110101199001011235');
    await waitFor(() => expect(screen.getByText(/该证件号已绑定其它账号/)).toBeTruthy());
  });

  it('格式不对时不发请求', async () => {
    const calls: Array<{ path: string; body: unknown }> = [];
    render(<VerifyIdentityBlock
      client={makeClient({ status: 200, body: { is_verified: true, status: 'verified' } }, calls)}
      onDone={() => {}} />);
    fill('赵六', '123');
    await waitFor(() => expect(screen.getByText(/15 或 18 位身份证号/)).toBeTruthy());
    expect(calls).toHaveLength(0);
  });
});
