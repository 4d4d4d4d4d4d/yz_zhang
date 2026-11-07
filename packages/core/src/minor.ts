import { GUARDIAN_MODE_LABEL, type GuardianMode, type Task } from './types';

/** SCN-144（214 号 spec）服务对象是未成年人的单：任务详情上的一句话，接单前就知道要求什么。两端同一句。 */
export function minorTaskLine(t: Pick<Task, 'minor_involved' | 'guardian_mode'> | null | undefined): string {
  if (!t?.minor_involved) return '';
  const mode = t.guardian_mode && t.guardian_mode in GUARDIAN_MODE_LABEL ? GUARDIAN_MODE_LABEL[t.guardian_mode as GuardianMode] : '';
  return `服务对象是未成年人${mode ? ` · ${mode}` : ''} · 接单要有平台审核通过的无犯罪记录证明`;
}

/** 发布页这一组选项换成请求体：没勾「服务对象是未成年人」时一项都不带（请求体与以前一样）。 */
export function minorPayload(on: boolean, mode: GuardianMode | '', consented: boolean):
  { minor_involved: true; guardian_mode: GuardianMode | ''; guardian_consented: boolean } | Record<string, never> {
  return on ? { minor_involved: true, guardian_mode: mode, guardian_consented: consented } : {};
}
