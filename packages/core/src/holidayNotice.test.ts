// ESCA-072（288 号 spec）放假通知原文 → 草稿
import { describe, expect, it } from 'vitest';
import { DEFAULT_MAKEUP_WEEKDAY, parseHolidayNotice } from './holidayNotice';

// 2025 年通知的写法（抬头、编号条目、括号注释、「至6日」省略月份、末尾的附言都照原样）
const NOTICE_2025 = `国务院办公厅关于2025年部分节假日安排的通知
各省、自治区、直辖市人民政府，国务院各部委、各直属机构：
经国务院批准，现将2025年元旦、春节、清明节、劳动节、端午节、中秋节和国庆节放假调休日期的具体安排通知如下。
一、元旦：1月1日（周三）放假1天，不调休。
二、春节：1月28日（农历除夕、周二）至2月4日（农历正月初七、周二）放假调休，共8天。1月26日（周日）、2月8日（周六）上班。
三、清明节：4月4日（周五）至6日（周日）放假，共3天。
四、劳动节：5月1日（周四）至5日（周一）放假调休，共5天。4月27日（周日）上班。
五、端午节：5月31日（周六）至6月2日（周一）放假，共3天。
六、国庆节、中秋节：10月1日（周三）至8日（周三）放假调休，共8天。9月28日（周日）、10月11日（周六）上班。
节假日期间，各地区、各部门要妥善安排好值班和安全、保卫等工作。`;

describe('parseHolidayNotice', () => {
  it('整份通知：放假的每一天、调休上班的每一天，标签取条目名', () => {
    const { items, unparsed } = parseHolidayNotice(NOTICE_2025, 2025);
    expect(unparsed).toEqual([]);
    const off = items.filter((i) => i.kind === 'off');
    const work = items.filter((i) => i.kind === 'workday');
    expect(off.length).toBe(1 + 8 + 3 + 5 + 3 + 8);
    expect(work.map((w) => w.day)).toEqual(['2025-01-26', '2025-02-08', '2025-04-27', '2025-09-28', '2025-10-11']);
    expect(work.every((w) => w.as_weekday === DEFAULT_MAKEUP_WEEKDAY)).toBe(true);
    expect(off.every((o) => o.as_weekday === null)).toBe(true);
    expect(items.find((i) => i.day === '2025-02-04')?.label).toBe('春节');
    expect(items.find((i) => i.day === '2025-04-06')?.label).toBe('清明节');
    expect(items.find((i) => i.day === '2025-06-01')?.label).toBe('端午节');
    expect(items.find((i) => i.day === '2025-10-08')?.label).toBe('国庆节、中秋节');
    expect(items.find((i) => i.day === '2025-10-11')?.label).toBe('国庆节、中秋节调休上班');
    expect(items.map((i) => i.day)).toEqual([...items.map((i) => i.day)].sort());
    expect(items.some((i) => i.day === '2025-01-27')).toBe(false);
  });

  it('跨年的日期写了年份就用那一年；不存在的日期不出', () => {
    const r = parseHolidayNotice('一、元旦：2025年12月31日至2026年1月2日放假。二、某节：2月30日放假1天。', 2026);
    expect(r.items.map((i) => i.day)).toEqual(['2025-12-31', '2026-01-01', '2026-01-02']);
    expect(r.unparsed).toEqual(['某节：2月30日放假1天。']);
  });

  it('括号里的注释即使写了日期也不算（如「2月9日为除夕」）', () => {
    const r = parseHolidayNotice('一、春节：2月10日（2月9日为除夕）至2月12日放假。', 2027);
    expect(r.items.map((i) => i.day)).toEqual(['2027-02-10', '2027-02-11', '2027-02-12']);
  });

  it('认不出日期的条目原样列出，不猜；没有编号的文字不算', () => {
    const r = parseHolidayNotice('随便一段话：放假了。\n一、春节：另行通知。', 2025);
    expect(r.items).toEqual([]);
    expect(r.unparsed).toEqual(['春节：另行通知。']);
  });
});
