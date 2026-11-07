// XAPP-007 统一执行器协议（161 号 spec）：拿下一步 → 执行 → 回报结果。
// Android 无障碍执行器、桌面执行器、iOS 快捷指令、测试用的模拟执行器都用这一个驱动循环，
// 只各自实现 `perform`（真正去点的那一下）。红线步与等待确认都不在这里做主：交给人。
import type { PlatformClient } from './client';
import type { XappCatalog, XappNext, XappPlan, XappPlanRules, XappPlanStep, XappStep } from './types';

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

// ------------------------------------------------------------------ XAPP-015 本机出计划（隐私沙箱）
// 与服务端 `app/modules/xapp/planner.py` 的 plan_by_rules 同一个算法、同一张规则表（来自 `/xapp/catalog`）；
// 两边对同一组例子出同样的计划（`xapp-plan-cases.json`，两边测试都读）。目标原文不离开这台设备。
function spans(text: string, word: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  if (!word) return out;
  for (let i = text.indexOf(word); i >= 0; i = text.indexOf(word, i + word.length)) out.push([i, i + word.length]);
  return out;
}

/** 只按规则出步骤（不含标签以外的文案），与服务端 plan_by_rules 一一对应 */
export function planXappSteps(goal: string, apps: string[], rules: XappPlanRules, labels: Record<string, string> = {},
                              redLine: ReadonlySet<string> = new Set()): XappPlanStep[] {
  const text = goal.trim();
  const hint = (app: string) => rules.apps.find((h) => h.app === app);
  const channels = (app: string) => [...(hint(app)?.channels ?? rules.default_channels)];
  const pick = (app: string, action: string) => {
    const ch = channels(app);
    return action === 'open' ? ch[0] : (ch.find((c) => c !== 'deeplink') ?? ch[ch.length - 1]);
  };
  const step = (app: string, action: string, intent: string, why: string): XappPlanStep => ({
    app, action, action_label: labels[action] ?? action, intent: intent.slice(0, 200), channel: pick(app, action),
    vision_where: 'device', red_line: redLine.has(action), why,
  });
  const openIntent = (app: string) => '打开' + (hint(app)?.names[0] ?? app);
  let mentions: Array<[number, string]> = [];
  for (const app of apps) {
    const pos = [app, ...(hint(app)?.names ?? [])].map((n) => (n ? text.indexOf(n) : -1)).filter((p) => p >= 0);
    if (pos.length) mentions.push([Math.min(...pos), app]);
  }
  mentions.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
  if (!mentions.length) mentions = [[0, apps[0]]];
  // App 的名字先占位：「支付宝」里的「支付」不是付款
  const names = new Set<string>([...rules.apps.flatMap((h) => h.names), ...apps]);
  const taken: Array<[number, number]> = [...names].flatMap((n) => spans(text, n));
  // 长词先认（同样长时红线在前）
  const pairs = rules.actions.flatMap((r) => r.words.map((w) => [w, r] as const)).sort((a, b) => b[0].length - a[0].length);
  const hits: Array<[number, string, string, string]> = [];
  for (const [w, rule] of pairs) {
    for (const [s, e] of spans(text, w)) {
      if (taken.some(([a, b]) => a < e && s < b)) continue;
      taken.push([s, e]);
      hits.push([s, rule.action, rule.intent, w]);
    }
  }
  hits.sort((a, b) => a[0] - b[0]);
  const steps: XappPlanStep[] = [];
  const opened = new Set<string>();
  for (const [pos, action, intent, word] of hits) {
    const app = [...mentions].reverse().find(([p]) => p <= pos)?.[1] ?? mentions[0][1];
    if (!opened.has(app)) {
      opened.add(app);
      steps.push(step(app, 'open', openIntent(app), '先打开要操作的 App'));
    }
    const last = steps[steps.length - 1];
    if (last && last.app === app && last.action === action) continue;
    steps.push(step(app, action, intent, `目标里有「${word}」`));
  }
  for (const [, app] of mentions) {
    if (!opened.has(app)) {
      opened.add(app);
      steps.push(step(app, 'open', openIntent(app), '目标里提到了它'));
    }
  }
  return steps.slice(0, rules.max_steps);
}

/** 隐私沙箱里出计划：不联网，结果与服务端的规则计划同一个形状，source 标成 device_rules */
export function planXappLocally(goal: string, grant: { id: number; apps: string[]; actions: string[] }, catalog: XappCatalog): XappPlan {
  const labels: Record<string, string> = {};
  for (const a of catalog.actions) labels[a.key] = a.label;
  for (const a of catalog.red_line) labels[a.key] = a.label;
  const red = new Set(catalog.red_line.map((a) => a.key));
  const steps = planXappSteps(goal, grant.apps, catalog.plan_rules, labels, red);
  const missing = [...new Set(steps.filter((s) => !s.red_line && !grant.actions.includes(s.action)).map((s) => s.action))].sort();
  const notes = ['隐私沙箱开着：这份计划是在本机按规则出的，目标原文没有发出去'];
  if (missing.length) notes.push(`这些动作还没授权：${missing.map((a) => labels[a] ?? a).join('、')}。先在授权里加上，或去掉那几步`);
  if (steps.some((s) => s.red_line)) notes.push('标了红线的步骤，智能体只把你带到那个页面，由你亲手完成');
  return { goal: goal.trim(), grant_id: grant.id, source: 'device_rules', steps, missing_actions: missing,
           ready: steps.length > 0 && missing.length === 0, notes };
}
