// TZ-063 客户端解析服务端时间的**唯一入口**（58 号 spec）。
//
// 病历：服务端此前给的是 `2026-09-20T08:00:00`——UTC 的值，但没有 `Z`。
// 而 JavaScript 的规矩是：ISO 8601 的**日期时间形式**不带偏移时按**本地时间**
// 解析（只有日期时才按 UTC）。于是
//
//     new Date('2026-09-20T08:00:00')   // 东八区：当成本地 08:00，实际差 8 小时
//
// 全站每一处时间显示都偏了用户所在时区的偏移量。有人在两个倒计时处发现了这件事，
// 各自就地补了个 `+ 'Z'`——**补丁本身就是缺陷报告**，其余七处没补。
//
// 现在服务端一律带 `Z`。这个函数仍然对「不带偏移」做防御性处理：
// 老客户端缓存里、导出的旧数据里、第三方回灌的数据里都可能还有裸值，
// 而把它们当本地时间解析**恰好是那个错**。

import { type Locale, resolveLocale } from './i18n';

/** 解析服务端时间。没有偏移的一律按 **UTC** 解释，不按本地时间。 */
export function parseServerTime(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') return new Date(value);
  const s = value.trim();
  // 只有日期（2026-09-20）时 JS 本来就按 UTC 解析，不动它
  const needsZone = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/.test(s);
  const d = new Date(needsZone ? `${s}Z` : s);
  return Number.isNaN(d.getTime()) ? null : d;
}

const LOCALE_TAG: Record<Locale, string> = { 'zh-CN': 'zh-CN', en: 'en-US' };

/** 日期 + 时分，按**浏览器所在时区**渲染。服务端只负责给 UTC。 */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseServerTime(value);
  if (!d) return '';
  const tag = LOCALE_TAG[resolveLocale(locale)];
  return new Intl.DateTimeFormat(tag, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    ...options,
  }).format(d);
}

/** 只要日期的场合（有效期、账单日）。 */
export function formatDate(
  value: string | number | Date | null | undefined,
  locale?: string,
): string {
  const d = parseServerTime(value);
  if (!d) return '';
  const tag = LOCALE_TAG[resolveLocale(locale)];
  return new Intl.DateTimeFormat(tag, { year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
}

/** 距离某个时刻还有多少毫秒；过期为负。倒计时用它，别自己 `new Date(x + 'Z')`。 */
export function millisUntil(value: string | number | Date | null | undefined): number {
  const d = parseServerTime(value);
  return d ? d.getTime() - Date.now() : 0;
}

/** 提交给服务端的时间：**一律带偏移**（`toISOString()` 出的是 `...Z`）。
 *
 *  `<input type="datetime-local">` 给出的是没有偏移的本地字符串
 *  （`2030-01-01T10:00`），直接发出去服务端会当 UTC——正是 TZ-062 那个洞的
 *  镜像。经过这里转换后发的是同一时刻的 UTC 表示。
 */
export function localInputToServerTime(localValue: string): string {
  if (!localValue) return '';
  const d = new Date(localValue);           // 无偏移字符串 → 按本地时间解析，这里正是想要的
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}
