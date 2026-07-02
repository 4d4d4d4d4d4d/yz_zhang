import { ApiError } from '@platform/core';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../store';

export default function Login() {
  const { client, setToken } = useApp();
  const nav = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState('');

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const res =
        mode === 'login'
          ? await client.login(phone, password)
          : await client.register(phone, password, nickname);
      setToken(res.token);
      nav('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>{mode === 'login' ? '登录' : '注册'}</h3>
        <form className="form" onSubmit={submit}>
          <label>
            手机号
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="13800000000" required />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
          </label>
          {mode === 'register' && (
            <>
              <label>
                昵称
                <input value={nickname} onChange={(e) => setNickname(e.target.value)} />
              </label>
              <p className="muted">开发环境短信验证码固定为 123456，已自动填入</p>
            </>
          )}
          {error && <p className="error">{error}</p>}
          <div className="row">
            <button type="submit">{mode === 'login' ? '登录' : '注册'}</button>
            <button type="button" className="ghost" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
              {mode === 'login' ? '没有账号？去注册' : '已有账号？去登录'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
