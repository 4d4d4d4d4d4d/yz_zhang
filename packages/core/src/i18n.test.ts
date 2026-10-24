import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE, ERROR_MESSAGE_ZH, SERVER_WORDED_CODES,
  errorMessage, formatMoney, resolveLocale,
} from './i18n';

describe('resolveLocale', () => {
  it('用户偏好优先于浏览器设置', () => {
    // 很多人的浏览器语言并不是他想看的语言（公司统一装机、二手设备）
    expect(resolveLocale('en-US,en;q=0.9', 'zh-CN')).toBe('zh-CN');
    expect(resolveLocale('zh-CN,zh;q=0.9', 'en')).toBe('en');
  });

  it('不支持的语种回落到默认，而不是报错或留空', () => {
    expect(resolveLocale('fr-FR,fr;q=0.9')).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(null, null)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale('')).toBe(DEFAULT_LOCALE);
  });

  it('繁体回落到简体而不是英文（产品决定）', () => {
    expect(resolveLocale('zh-TW,zh-HK;q=0.9,en;q=0.8')).toBe('zh-CN');
  });
});

describe('errorMessage', () => {
  it('认识的 code 用本地文案', () => {
    expect(errorMessage('insufficient_balance', '服务端说的')).toBe(
      ERROR_MESSAGE_ZH.insufficient_balance,
    );
  });

  it('拼接消息的 code 优先用服务端文案——客户端编不出等价的', () => {
    const code = SERVER_WORDED_CODES[0];
    expect(errorMessage(code, '「保洁」不在该助理的能力范围内')).toBe(
      '「保洁」不在该助理的能力范围内',
    );
  });

  it('不认识的 code 回落服务端消息，而不是把 code 摆给用户看', () => {
    // 把 insufficient_balance 摆给用户看，和什么都不说差不多
    expect(errorMessage('never_seen_code', '余额不太够')).toBe('余额不太够');
    expect(errorMessage('never_seen_code', '')).toBe(ERROR_MESSAGE_ZH.bad_request);
  });

  it('什么都没有时也要给一句人话', () => {
    expect(errorMessage(undefined, undefined)).toBe(ERROR_MESSAGE_ZH.bad_request);
    expect(errorMessage(undefined, undefined).length).toBeGreaterThan(0);
  });
});

describe('formatMoney', () => {
  it('整数分只在展示层格式化', () => {
    expect(formatMoney(12345)).toBe('¥123.45');
    expect(formatMoney(0)).toBe('¥0.00');
    expect(formatMoney(-500)).toBe('¥-5.00');
  });

  it('换 locale 换格式，但金额本身不变', () => {
    expect(formatMoney(12345, 'en')).toContain('123.45');
  });
});
