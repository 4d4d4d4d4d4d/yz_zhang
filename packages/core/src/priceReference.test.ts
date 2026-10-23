import { describe, expect, it } from 'vitest';
import { priceReferenceLine } from './priceReference';

describe('KB-064 参考价那一句', () => {
  const base = { sample_size: 9, p50_cents: 5000, min_cents: 5000, max_cents: 22000 };
  it('有样本照旧；集中时接上去重说明；不集中不接', () => {
    expect(priceReferenceLine(base)).toBe('同类闭环任务 9 单：中位价 ¥50.00（¥50.00 ~ ¥220.00）');
    expect(priceReferenceLine({ ...base, concentrated: true, note: '按发布方去重后中位价是 ¥180.00' }))
      .toBe('同类闭环任务 9 单：中位价 ¥50.00（¥50.00 ~ ¥220.00）。按发布方去重后中位价是 ¥180.00');
    expect(priceReferenceLine({ ...base, concentrated: false, note: '' })).not.toContain('。');
    expect(priceReferenceLine({ ...base, concentrated: false, note: '有说明但不集中' })).not.toContain('有说明');
  });
  it('没有样本给服务端的话；畸形响应给空串', () => {
    expect(priceReferenceLine({ sample_size: 0, message: '暂无同类闭环数据' })).toBe('暂无同类闭环数据');
    expect(priceReferenceLine(null)).toBe('');
    expect(priceReferenceLine({} as never)).toBe('');
    expect(priceReferenceLine({ p50_cents: 5000 } as never)).toBe('');
  });
});
