import type { CaptchaConfig } from '@platform/core';
import { useEffect, useRef, useState } from 'react';

/** CAP-012 人机验证挑战。
 *
 * hCaptcha / Cloudflare Turnstile / 腾讯云验证码都是同一个形状：
 * **加载脚本 → 用站点公钥渲染到一个容器 → 回调拿 token**。
 * 所以这里只按这个形状实现一次，接哪家只改环境变量。
 *
 * 没有配脚本地址时（沙箱、自建）退化成一个可输入的令牌框，
 * 并**如实说明它是什么**——不假装是一个真的滑块。
 */
export default function CaptchaChallenge({
  config,
  onToken,
}: {
  config: CaptchaConfig;
  onToken: (token: string) => void;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const [manual, setManual] = useState('');

  useEffect(() => {
    if (!config.script_url || !config.site_key || !mount.current) return;
    const existing = document.querySelector(`script[src="${config.script_url}"]`);
    if (!existing) {
      const s = document.createElement('script');
      s.src = config.script_url;
      s.async = true;
      document.head.appendChild(s);
    }
    // 供应商脚本约定：扫描带 data-sitekey 的容器并在通过时回调。
    // 回调名挂到 window 上是这三家共同的做法。
    const cbName = `__captchaDone_${Date.now()}`;
    (window as unknown as Record<string, unknown>)[cbName] = (token: string) =>
      onToken(token);
    mount.current.setAttribute('data-sitekey', config.site_key);
    mount.current.setAttribute('data-callback', cbName);
    return () => {
      delete (window as unknown as Record<string, unknown>)[cbName];
    };
  }, [config, onToken]);

  if (config.script_url && config.site_key) {
    return (
      <div>
        <p className="muted">为确认你不是自动程序，请完成下方验证</p>
        <div ref={mount} className="g-recaptcha h-captcha cf-turnstile" />
      </div>
    );
  }

  // 没有供应商脚本：诚实地说明这是什么，而不是画一个假的滑块
  return (
    <label>
      人机验证令牌（当前为 <code>{config.provider}</code> 实现，无供应商挑战页）
      <input
        value={manual}
        onChange={(e) => {
          setManual(e.target.value);
          onToken(e.target.value);
        }}
        placeholder="粘贴验证令牌"
      />
    </label>
  );
}
