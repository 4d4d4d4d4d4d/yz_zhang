// XAPP-007 统一执行器协议（161 号 spec）：拿下一步 → 执行 → 回报结果。
// Android 无障碍执行器、桌面执行器、iOS 快捷指令、测试用的模拟执行器都用这一个驱动循环，
// 只各自实现 `perform`（真正去点的那一下）。红线步与等待确认都不在这里做主：交给人。
import type { PlatformClient } from './client';
import type { XappNext, XappStep } from './types';

export interface DriveOptions {
  /** 执行一步：返回是否成功与一句结果摘要（敏感内容会被服务端再脱敏一次） */
  perform: (step: XappStep) => Promise<{ ok: boolean; summary: string }>;
  /** 红线步：把人带到那个页面（例如打开付款页），等本人亲手做完 */
  handoff?: (step: XappStep) => Promise<void>;
  /** 最多走多少次循环，防止失控 */
  maxLoops?: number;
}

/** 一直走到需要人（确认 / 红线 / 失败交还）或结束为止，返回最后的状态。 */
export async function driveXappRun(client: PlatformClient, runId: number, opts: DriveOptions): Promise<XappNext> {
  const limit = opts.maxLoops ?? 100;
  for (let i = 0; i < limit; i += 1) {
    const next = await client.xappNext(runId);
    if (next.state === 'execute' && next.step) {
      let out: { ok: boolean; summary: string };
      try {
        out = await opts.perform(next.step);
      } catch (e) {
        out = { ok: false, summary: e instanceof Error ? e.message : '执行器出错' };
      }
      await client.xappReport(runId, next.step.id, out.ok, out.summary);
      continue;
    }
    if (next.state === 'handoff' && next.step && opts.handoff) await opts.handoff(next.step);
    return next;
  }
  return { state: 'running', reason: '循环次数用完，暂停在这里' };
}
