// KB-063b（326 号 spec）与服务端同一条判据：标点凑长度、够长的空话都不算具体。
import { describe, expect, it } from 'vitest';
import { lessonSpecific } from './lessons';

describe('KB-063b lessonSpecific', () => {
  it.each([
    ['不行', '', false], ['不满意！！', '', false], ['不行！！！！！', '', false], ['差。。。 。。。', '', false],
    ['做得不好请重做', '', false], ['完全不符合要求！', '', false], ['不是我想要的', '', false],
    ['没有拍完工照片', '', true], ['卫生间地漏没清', '', true], ['不行', '窗户要擦干净再拍照', true],
  ] as Array<[string, string, boolean]>)('%j / %j → %s', (r, v, want) => { expect(lessonSpecific(r, v)).toBe(want); });
});
