/**
 * ESCA-072（288 号 spec）把国务院办公厅「关于 X 年部分节假日安排的通知」原文解析成放假 / 调休草稿。
 *
 * 通知的写法多年不变：「二、春节：1月28日（农历除夕、周二）至2月4日（农历正月初七、周二）放假调休，共8天。
 * 1月26日（周日）、2月8日（周六）上班。」——逐条认出「放假」前面的日期（「至」表示连续几天）和「上班」前面的日期。
 * 只出草稿：主管核对、改「按周几的排班」后才保存；认不出的条目原样列在 `unparsed` 里，不猜。
 */

export interface HolidayDraft {
  /** YYYY-MM-DD（北京时间的日期） */
  day: string;
  kind: 'off' | 'workday';
  label: string;
  /** 调休上班按周几的排班（0=周一）；通知里不写，默认按周五，主管可改 */
  as_weekday: number | null;
}

export interface HolidayNoticeParse {
  items: HolidayDraft[];
  /** 编了号却一个日期都没认出来的条目，原样给主管看 */
  unparsed: string[];
}

export const DEFAULT_MAKEUP_WEEKDAY = 4;

const pad = (n: number) => String(n).padStart(2, '0');

function iso(year: number, month: number, day: number): string | null {
  const d = new Date(Date.UTC(year, month - 1, day));
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) return null;
  return `${year}-${pad(month)}-${pad(day)}`;
}

interface Token { year: number; month: number; day: number; index: number; end: number }

/** 认出一段话里的日期：「1月28日」「6日」（沿用前一个的月份）「2025年12月31日」 */
function dates(text: string, year: number): Token[] {
  const out: Token[] = [];
  let curYear = year;
  let curMonth = 0;
  const re = /(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日/g;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m[1]) curYear = Number(m[1]);
    if (m[2]) curMonth = Number(m[2]);
    if (!curMonth) continue;
    out.push({ year: curYear, month: curMonth, day: Number(m[3]), index: m.index, end: m.index + m[0].length });
  }
  return out;
}

function daysBetween(a: Token, b: Token): string[] {
  const out: string[] = [];
  const start = Date.UTC(a.year, a.month - 1, a.day);
  const end = Date.UTC(b.year, b.month - 1, b.day);
  if (end < start || end - start > 31 * 86400000) return out;
  for (let t = start; t <= end; t += 86400000) {
    const d = new Date(t);
    out.push(`${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`);
  }
  return out;
}

export function parseHolidayNotice(text: string, year: number): HolidayNoticeParse {
  // 括号里是「周三」「农历除夕」之类的注释，先去掉，免得干扰
  const clean = text.replace(/（[^）]*）|\([^)]*\)/g, '');
  // 只读编了号的条目（「一、」「二、」……）；抬头「各省、自治区……：」与开头那句不算
  const marks = [...clean.matchAll(/(?:^|[\s。；])[一二三四五六七八九十]+、/g)];
  const parts = marks.map((m, k) => clean.slice(m.index! + m[0].length, k + 1 < marks.length ? marks[k + 1].index : undefined).trim());
  const byDay = new Map<string, HolidayDraft>();
  const unparsed: string[] = [];
  for (const part of parts) {
    const colon = part.search(/[：:]/);
    if (colon <= 0) continue;
    const label = part.slice(0, colon).trim().slice(0, 30);
    const body = part.slice(colon + 1);
    let found = 0;
    for (const sentence of body.split(/[。；;]/)) {
      const offAt = sentence.indexOf('放假');
      const workAt = sentence.indexOf('上班');
      if (offAt >= 0 && (workAt < 0 || offAt < workAt)) {
        const ds = dates(sentence.slice(0, offAt), year);
        const ranged = ds.length >= 2 && /至|到|—|-/.test(sentence.slice(ds[0].end, ds[1].index));
        const days = ranged ? daysBetween(ds[0], ds[1]) : ds.map((d) => iso(d.year, d.month, d.day)).filter((d): d is string => !!d);
        for (const day of days) {
          byDay.set(day, { day, kind: 'off', label, as_weekday: null });
          found += 1;
        }
      } else if (workAt >= 0) {
        for (const d of dates(sentence.slice(0, workAt), year)) {
          const day = iso(d.year, d.month, d.day);
          if (!day) continue;
          byDay.set(day, { day, kind: 'workday', label: `${label}调休上班`.slice(0, 40), as_weekday: DEFAULT_MAKEUP_WEEKDAY });
          found += 1;
        }
      }
    }
    if (found === 0) unparsed.push(part.slice(0, 80));
  }
  const items = [...byDay.values()].sort((a, b) => a.day.localeCompare(b.day));
  return { items, unparsed };
}
