// REG-002（222 号 spec）App 根组件：取当前用户失败时只在服务端明确不认登录时清 token。
// App 根组件自己 new client（读 BASE_URL），登录态只在内存里，没法在测试里塞一个已登录的状态进去；
// 判定本身由共享 SDK 的 `isAuthRejection` 测（packages/core/src/session.test.ts），这里守住 App 真的用了它。
import { readFileSync } from 'fs';

describe('REG-002 App 不因断网把人登出', () => {
  it('client.me() 的 catch 先问 isAuthRejection 再清 token', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    const line = src.split('\n').find((l) => l.includes('client.me().then(setMe)'));
    expect(line).toBeTruthy();
    expect(line).toMatch(/\.catch\(\(e\) => \{ if \(isAuthRejection\(e\)\) setToken\(null\); \}\)/);
    // 以前是 `.catch(() => setToken(null))`：任何失败（含信号一抖）都登出
    expect(src).not.toContain('.catch(() => setToken(null))');
  });
});
