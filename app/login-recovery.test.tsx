// ACC-041 App 登录页：登录是登录，注册是注册（77 号 spec）。
//
// 三分类闸门（CLI-082）只能证明「有某个端在调 smsLogin」——web 调了它就绿。
// 它证明不了 App 这一侧有没有退回原来的做法，而原来的做法是：
//
//   await client.login(phone, password).catch(() => client.register(...))
//
// 密码打错走到注册、手机号打错一位静默注册出一个新账号。
// 这一层只能用 App 自己的行为测试钉住（V96 的教训：闸门选错层等于没有）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { LoginScreen } from './App';

type Call = { method: string; path: string; body: unknown };

/** 登录一律失败（密码错），其余按表返回。 */
function makeClient(calls: Call[], overrides: Record<string, unknown> = {}): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    if (path in overrides) {
      return { ok: true, status: 200, text: async () => JSON.stringify(overrides[path]) };
    }
    if (path === '/auth/login') {
      return {
        ok: false, status: 401,
        text: async () => JSON.stringify({ detail: { code: 'bad_credentials', message: '手机号或密码错误' } }),
      };
    }
    return { ok: true, status: 200, text: async () => JSON.stringify({}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => null, fetchImpl });
}

describe('ACC-041 登录失败不许悄悄注册', () => {
  it('密码错就说密码错，不会转头去注册', async () => {
    const calls: Call[] = [];
    render(<LoginScreen client={makeClient(calls)} onToken={() => {}} />);

    fireEvent.changeText(screen.getByPlaceholderText('手机号'), '13800000001');
    fireEvent.changeText(screen.getByPlaceholderText('密码'), 'wrongpass');
    fireEvent.press(screen.getByText('登录'));

    await waitFor(() => expect(screen.getByText('手机号或密码错误')).toBeTruthy());
    // **这一条是要害**：不许出现注册请求
    expect(calls.some((c) => c.path === '/auth/register')).toBe(false);
  });

  it('忘记密码走的是重置，不是注册', async () => {
    const calls: Call[] = [];
    render(<LoginScreen
      client={makeClient(calls, { '/auth/send-code': { sent: true, expires_in: 300, dev_code: '123456' } })}
      onToken={() => {}} />);

    fireEvent.press(screen.getByText('忘记密码'));
    fireEvent.changeText(screen.getByPlaceholderText('手机号'), '13800000001');
    fireEvent.press(screen.getByText('获取验证码'));
    // scene 跟着用途走
    await waitFor(() => {
      const sent = calls.find((c) => c.path === '/auth/send-code');
      expect((sent!.body as { scene: string }).scene).toBe('reset');
    });

    fireEvent.changeText(screen.getByPlaceholderText('新密码'), 'newpass12345');
    fireEvent.press(screen.getByText('重置密码'));
    await waitFor(() => expect(calls.some((c) => c.path === '/auth/reset-password')).toBe(true));
    expect(calls.some((c) => c.path === '/auth/register')).toBe(false);
  });

  it('验证码登录不需要密码框', async () => {
    const calls: Call[] = [];
    render(<LoginScreen client={makeClient(calls)} onToken={() => {}} />);
    fireEvent.press(screen.getByText('验证码登录'));
    expect(screen.queryByPlaceholderText('密码')).toBeNull();
    expect(screen.getByPlaceholderText('短信验证码')).toBeTruthy();
  });
});

 it('注册必须提交 verify 场景验证码', async () => {
    const calls: Call[] = [];
    render(<LoginScreen client={makeClient(calls, { '/auth/send-code': { expires_in: 600, dev_code: '123456' }, '/auth/register': { token: 'test-token' } })} onToken={() => {}} />);
    fireEvent.press(screen.getByText('没有账号？注册'));
    fireEvent.changeText(screen.getByPlaceholderText('手机号'), '13800000991');
    fireEvent.changeText(screen.getByPlaceholderText('密码'), 'testpass123');
    fireEvent.press(screen.getByText('获取验证码'));
    await waitFor(() => expect(calls.find(c => c.path === '/auth/send-code')).toBeTruthy());
    expect((calls.find(c => c.path === '/auth/send-code')?.body as { scene: string }).scene).toBe('verify');
    fireEvent.changeText(screen.getByPlaceholderText('短信验证码'), '829143');
    fireEvent.press(screen.getByText('注册'));
    await waitFor(() => expect(calls.find(c => c.path === '/auth/register')).toBeTruthy());
    expect((calls.find(c => c.path === '/auth/register')?.body as { sms_code: string }).sms_code).toBe('829143');
 });
