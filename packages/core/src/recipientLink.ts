/** SCN-122（356 号 spec）服务对象自己看进度：发单人面板与免登录进度页两端共用的文案。 */
import { asList } from './decompose';
import { formatDateTime } from './time';
import type { RecipientLinkStatus, RecipientProgress } from './types';

export const RECIPIENT_LINK_DAYS = [1, 3, 7, 14] as const;

/** 发单人面板上一行说清链接现在怎样 */
export function recipientLinkLine(s: RecipientLinkStatus | null | undefined): string {
  if (!s || s.state === 'none') return '还没有生成：生成后用微信等发给服务对象本人，对方不用登录就能看谁来、几点、到没到';
  const seen = s.view_count > 0
    ? `已被打开 ${s.view_count} 次${s.last_viewed_at ? `，最近一次 ${formatDateTime(s.last_viewed_at)}` : ''}`
    : '还没被打开过';
  if (s.state === 'active') return `链接有效到 ${formatDateTime(s.expires_at)}；${seen}`;
  if (s.state === 'expired') return `链接已过期；${seen}。要的话重新生成一条`;
  return `链接已作废；${seen}。要的话重新生成一条`;
}

/** 生成后给发单人的完整链接（网页地址 + /r/令牌） */
export function recipientLinkUrl(origin: string, path: string): string {
  return `${origin.replace(/\/+$/, '')}${path.startsWith('/') ? path : `/${path}`}`;
}

/** 进度页上的几行人话：谁来、哪天几点、到没到 */
export function recipientProgressLines(p: RecipientProgress): string[] {
  // APP-091 响应畸形（缺字段、不是对象）也不能把页面打白：缺什么就少一行
  if (!p || typeof p !== 'object' || typeof p.phase_text !== 'string') return [];
  const helpers = asList<RecipientProgress['helpers'][number]>(p.helpers);
  const lines: string[] = [];
  const who = p.recipient_label ? `${p.recipient_label}，` : '';
  lines.push(`${who}这一单${p.phase_text}`);
  if (helpers.length) {
    const names = helpers.map((h) => `${h.name}${h.verified ? '（已实名）' : ''}${h.work_date ? ` ${h.work_date}` : ''}`);
    lines.push(`来的人：${names.join('、')}`);
  }
  const when = [p.work_date ? `${p.work_date}${p.days > 1 ? ` 起共 ${p.days} 天` : ''}` : '',
    p.shift_start && p.shift_end ? `${p.shift_start}~${p.shift_end}` : ''].filter(Boolean).join(' ');
  if (when) lines.push(`时间：${when}（北京时间）`);
  else if (p.deadline) lines.push(`最晚 ${formatDateTime(p.deadline)} 前`);
  if (Number(p.visits_planned) > 0) lines.push(`上门：计划 ${p.visits_planned} 次，已回报 ${p.visits_reported} 次`);
  lines.push(p.last_arrival_at ? `最近一次到达：${formatDateTime(p.last_arrival_at)}` : '还没有到达记录');
  return lines;
}
