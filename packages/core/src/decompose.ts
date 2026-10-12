// AI-DEC-040~048 逐层拆解树的共享文案与小工具（106 号 spec）。两端同一份，不各写各的。
import type { Decomposition, DecompositionNode, ExecutorKind, LeafCriterion } from './types';

export const EXECUTOR_KIND_LABEL: Record<ExecutorKind, string> = {
  ai_closable: 'AI 可闭环',
  needs_human: '找人做',
  needs_expert: '需要持证专家',
  needs_machine: '需要设备',
  unknown: '待定：谁来做',
};

export const LEAF_CRITERION_LABEL: Record<LeafCriterion, string> = {
  deliverable: '交付物',
  acceptance: '验收标准',
  single_owner: '单一责任主体',
  budget: '可托管的预算',
};

/** 一步的执行主体标签。需要资质时说出是什么资质（「需要律师」比「需要专家」有用）。 */
export function executorLabel(node: DecompositionNode): string {
  if (!node.executor_kind) return '';
  if (node.executor_kind === 'needs_expert' && node.required_cert) return `需要${node.required_cert}`;
  return EXECUTOR_KIND_LABEL[node.executor_kind];
}

/** AI-DEC-048 拆解从哪来。**回落模板必须看得见**：模型不可用时界面要说出来。 */
export function decompositionSourceLabel(dec: Decomposition): string {
  if (dec.fallback) return 'AI 模型暂时不可用，以下按平台模板拆出';
  const s = dec.source;
  if (s.startsWith('anthropic:') || s === 'stub-model') return 'AI 逐层拆解';
  if (s === 'seed_template' || s === 'keyword_match') return '平台模板';
  if (s === 'closed_loop_experience') return '同类任务的成功经验';
  if (s === 'generic') return '通用三段式模板';
  return s || '—';
}

export function childrenOf(nodes: DecompositionNode[], parent: number | null): DecompositionNode[] {
  return nodes.filter((n) => n.parent === parent);
}

/** 没有子步骤的节点：要么是叶子，要么是还没拆完/停下来的步骤。 */
export function isOpenEnd(nodes: DecompositionNode[], node: DecompositionNode): boolean {
  return !nodes.some((n) => n.parent === node.id);
}
