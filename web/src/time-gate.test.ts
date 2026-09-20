// TZ-063 客户端不许自己解析服务端时间。
//
// 病历：服务端此前给的 UTC 时间不带 `Z`，而 JS 对不带偏移的 ISO 日期时间
// 按**本地时间**解析。全站九处 `new Date(服务端字符串)` 里，只有两处倒计时
// 被发现并就地补了 `+ 'Z'`——因为倒计时错了会算成负数，肉眼可见；
// 而「这条流水是几点」错 8 小时，没有人会立刻察觉。
//
// 所以这里不是「建议用 formatDateTime」，是**禁止**再出现带参数的 `new Date(...)`：
// 一个能直接这么写的代码库，迟早会有人这么写，然后错一个时区。
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOTS = [resolve(__dirname), resolve(__dirname, '../../app')];
const EXT = /\.(ts|tsx)$/;
// `new Date()` 取当前时间没问题；带参数的才是病灶
const NEW_DATE_WITH_ARG = /new Date\(\s*[^)\s]/;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (EXT.test(name)) out.push(full);
  }
  return out;
}

describe('TZ-063 时间解析只有一个入口', () => {
  const files = ROOTS.flatMap((r) => {
    try { return walk(r); } catch { return []; }
  });

  it('扫描器真的扫到了文件（扫不到就等于没有闸门）', () => {
    expect(files.length).toBeGreaterThan(15);
    expect(files.some((f) => f.endsWith('Wallet.tsx'))).toBe(true);
    expect(files.some((f) => f.endsWith('App.tsx'))).toBe(true);
  });

  it('web/ 与 app/ 源码里没有带参数的 new Date(...)', () => {
    const offenders: string[] = [];
    for (const file of files) {
      // 这个闸门文件自己要写出那个模式才能描述它
      if (file.endsWith('time-gate.test.ts')) continue;
      readFileSync(file, 'utf-8').split('\n').forEach((line, i) => {
        if (NEW_DATE_WITH_ARG.test(line)) offenders.push(`${file}:${i + 1} ${line.trim()}`);
      });
    }
    expect(offenders, '请改用 @platform/core 的 parseServerTime / formatDateTime / millisUntil').toEqual([]);
  });
});
