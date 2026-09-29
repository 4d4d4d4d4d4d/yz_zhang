// ACC-041 登录页的三条路：密码登录 / 验证码登录 / 忘记密码（77 号 spec）。
//
// 探针：`resetPassword` / `smsLogin` / `sendSmsCode` 三条端到端都在，
// 而登录页上只有「密码登录」和「注册」。V68 补的是**登录之后**改密码——
// 忘了密码的人登不进去，那个入口对他毫无意义。
// 这是「钱能进不能出」的账号版。
import { ApiError, apiErrorText, type CaptchaConfig } from '@platform/core';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import CaptchaChallenge from '../CaptchaChallenge';
import { useApp } from '../store';

type Mode = 'login' | 'register' | 'sms' | 'reset';

const TITLES: Record<Mode, string> = {
  login: '登录',
  register: '注册',
  sms: '验证码登录',
  reset: '重置密码',
};

export default function Login() {
  const { client, setToken } = useApp();
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>('login');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [sent, setSent] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  // CAP-003 反应式：**不**预先问「我需不需要验证」——那等于把「这个 IP 已经
  // 触发风控」告诉任何人。只有服务端真的要求了才拉配置并渲染挑战
  const [captcha, setCaptcha] = useState<CaptchaConfig | null>(null);
  const [captchaToken, setCaptchaToken] = useState('');

  function switchTo(next: Mode) {
    setMode(next);
    setError('');
    setDone('');
    setSent('');
    setSmsCode('');
  }

  async function sendCode() {
    setError('');
    setDone('');
    try {
      // scene 要跟着用途走：找回密码与登录是两个场景，
      // 服务端据此决定验证码的用途与有效期
      const r = await client.sendSmsCode(phone, mode === 'reset' ? 'reset' : 'login');
      // 沙箱桩会回显验证码（19/27 号 spec 的既有约定）。有它就填上，
      // 省掉一次手抄；生产上不返回这个字段，提示语也就不出现
      if (r.dev_code) setSmsCode(r.dev_code);
      setSent(`验证码已发送，${r.expires_in} 秒内有效${r.dev_code ? '（开发态已自动填入）' : ''}`);
    } catch (err) {
      setError(apiErrorText(err));
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setDone('');
    try {
      if (mode === 'reset') {
        await client.resetPassword(phone, smsCode, password);
        // 重置完不自动登录：新密码刚设好，让他用一次，确认自己记住了。
        // switchTo 会清掉提示，所以先切换、再写这句话
        switchTo('login');
        setDone('密码已重置，请用新密码登录');
        return;
      }
      const res =
        mode === 'login' ? await client.login(phone, password, captchaToken)
        : mode === 'sms' ? await client.smsLogin(phone, smsCode)
        : await client.register(phone, password, nickname);
      setToken(res.token);
      nav('/');
    } catch (err) {
      if (err instanceof ApiError && err.code === 'captcha_required') {
        // 服务端要求人机验证：拉配置、渲染挑战，让用户能**自证是真人**再重试。
        // 少了这一步，接上真实验证码后连续输错几次密码的用户就被永久挡在门外
        setCaptcha(await client.captchaConfig().catch(() => null));
        setCaptchaToken('');
        setError('请完成人机验证后重试');
        return;
      }
      setError(apiErrorText(err));
    }
  }

  const needsPassword = mode === 'login' || mode === 'register' || mode === 'reset';
  const needsCode = mode === 'sms' || mode === 'reset';

  return (
    <div className="page">
      <div className="card">
        <h3>{TITLES[mode]}</h3>
        <form className="form" onSubmit={submit}>
          <label>
            手机号
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="13800000000" required />
          </label>
          {needsPassword && (
            <label>
              {mode === 'reset' ? '新密码' : '密码'}
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                     minLength={6} required />
            </label>
          )}
          {needsCode && (
            <label>
              短信验证码
              <span className="row">
                <input className="grow" value={smsCode} onChange={(e) => setSmsCode(e.target.value)}
                       required data-testid="sms-code" />
                <button type="button" className="ghost" onClick={() => void sendCode()}
                        disabled={!phone}>获取验证码</button>
              </span>
            </label>
          )}
          {sent && <p className="muted" data-testid="sms-sent">{sent}</p>}
          {mode === 'register' && (
            <label>
              昵称
              <input value={nickname} onChange={(e) => setNickname(e.target.value)} />
            </label>
          )}
          {captcha && mode === 'login' && (
            <CaptchaChallenge config={captcha} onToken={setCaptchaToken} />
          )}
          {error && <p className="error">{error}</p>}
          {done && <p className="muted" data-testid="login-done">{done}</p>}
          <div className="row">
            <button type="submit">{TITLES[mode]}</button>
            {mode !== 'register' && (
              <button type="button" className="ghost" onClick={() => switchTo('register')}>没有账号？去注册</button>
            )}
            {mode !== 'login' && (
              <button type="button" className="ghost" onClick={() => switchTo('login')}>用密码登录</button>
            )}
            {mode !== 'sms' && (
              <button type="button" className="ghost" onClick={() => switchTo('sms')}>验证码登录</button>
            )}
            {mode !== 'reset' && (
              <button type="button" className="ghost" onClick={() => switchTo('reset')}>忘记密码</button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
