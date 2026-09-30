// APP-060 类型层面的钉子：**必填字段由类型保证，不靠人记得**。
//
// V77 把 ip_assignment 改成服务端必填时，Web、测试、四个闭环脚本都改了，
// **App 漏了**——而 App 没有测试、CI 只做 tsc，漏一个字段在 `Partial<Task>`
// 面前不是类型错误。于是 App 上的「发布」按钮每次点击都返回 400，
// 一直到 V88 才被探针发现（63 号 spec）。
//
// 这个文件放在 `web/src/` 而不是 `packages/core/src/`，是因为**只有这里真的过
// `tsc`**：core 的测试只被 vitest 转译，不做类型检查——钉在那儿等于没钉。
// 这本身就是这一批的教训的又一个实例：**检查要放在真的会执行的地方。**
import { PlatformClient } from '@platform/core';
import { describe, expect, it, vi } from 'vitest';

const client = new PlatformClient({
  baseUrl: '', getToken: () => null,
  fetchImpl: vi.fn(async () => ({ ok: true, status: 200, text: async () => '{}' })) as unknown as typeof fetch,
});

describe('SDK 契约（类型层）', () => {
  it('createTask 漏 ip_assignment 编译不过', () => {
    // @ts-expect-error ip_assignment 是必需参数。这一行本身就是断言：
    // 哪天它又变回可选，这个 ts-expect-error 会变成「未使用」而让 tsc 失败。
    const missing = () => client.createTask({ title: 'x', category: '跑腿' });
    const complete = () => client.createTask({
      title: 'x', category: '跑腿', ip_assignment: 'assign',
    });
    expect(typeof missing).toBe('function');
    expect(typeof complete).toBe('function');
  });
});
