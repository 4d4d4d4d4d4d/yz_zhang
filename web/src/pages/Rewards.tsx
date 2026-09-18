// GRW 用户侧运营页：新人任务进度 / 我的券 / 领券 / 邀请战绩。
import { fmtYuan, type CouponTemplate, type MyCoupon } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

type Newcomer = {
  steps: Array<{ key: string; label: string; done: boolean }>;
  finished: number;
  total: number;
  completed: boolean;
};
type Referrals = {
  referral_code: string;
  invited_count: number;
  achieved_count: number;
  blocked_count: number;
  earned_cents: number;
  levels: number;
};

function couponValue(c: { amount_cents: number; percent_bps: number; max_discount_cents: number }) {
  if (c.amount_cents > 0) return `减 ${fmtYuan(c.amount_cents)}`;
  return `${(c.percent_bps / 100).toFixed(1)}% 折，最高减 ${fmtYuan(c.max_discount_cents)}`;
}

export default function Rewards() {
  const { client } = useApp();
  const [newcomer, setNewcomer] = useState<Newcomer | null>(null);
  const [mine, setMine] = useState<MyCoupon[]>([]);
  const [offers, setOffers] = useState<CouponTemplate[]>([]);
  const [ref, setRef] = useState<Referrals | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [n, m, o, r] = await Promise.all([
        client.newcomerProgress(),
        client.myCoupons(),
        client.availableCoupons(),
        client.myReferrals(),
      ]);
      setNewcomer(n);
      setMine(m.coupons);
      setOffers(o.coupons);
      setRef(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  async function claim(id: number) {
    setError('');
    try {
      await client.claimCoupon(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '领取失败');
    }
  }

  return (
    <div className="page">
      {error && <div className="card error">{error}</div>}

      {newcomer && (
        <div className="card">
          <h3>新人任务 {newcomer.finished}/{newcomer.total}</h3>
          <div className="progress-bar">
            <div style={{ width: `${(newcomer.finished / newcomer.total) * 100}%` }} />
          </div>
          <div className="list" style={{ marginTop: 8 }}>
            {newcomer.steps.map((s) => (
              <p key={s.key} className="muted">{s.done ? '✅' : '⬜️'} {s.label}</p>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h3>可领取的券</h3>
        {offers.length === 0 && <p className="muted">暂无可领取的券</p>}
        <div className="list">
          {offers.map((c) => (
            <div key={c.id} className="task-item">
              <div>
                <strong>{c.title}</strong>
                <p className="muted">
                  {couponValue(c)}
                  {c.min_order_cents > 0 && ` · 满 ${fmtYuan(c.min_order_cents)} 可用`}
                  {c.category && ` · 限「${c.category}」`}
                  {c.newcomer_only && ' · 仅新用户'}
                </p>
              </div>
              <button onClick={() => void claim(c.id)}>领取</button>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>我的券</h3>
        {mine.length === 0 && <p className="muted">还没有券</p>}
        <div className="list">
          {mine.map((c) => (
            <div key={c.id} className="task-item">
              <div>
                <strong>{c.title}</strong>
                <p className="muted">
                  {couponValue(c)} · 有效期至 {new Date(c.expires_at).toLocaleDateString()}
                </p>
              </div>
              <span className={`badge ${c.status === 'unused' ? 'ok' : ''}`}>
                {c.status === 'unused' ? '可用' : c.status === 'used' ? '已使用' : '已过期'}
              </span>
            </div>
          ))}
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          托管资金时可选用一张券，一单限用一张；订单取消后券自动退回。
        </p>
      </div>

      {ref && (
        <div className="card">
          <h3>邀请好友</h3>
          <p className="row">
            <span className="grow">我的邀请码：<strong>{ref.referral_code}</strong></span>
            <button className="ghost"
                    onClick={() => void navigator.clipboard?.writeText(ref.referral_code)}>
              复制
            </button>
          </p>
          <p className="muted">
            已邀请 {ref.invited_count} 人 · 达成 {ref.achieved_count} 人 ·
            累计奖励 {fmtYuan(ref.earned_cents)}
            {ref.blocked_count > 0 && ` · ${ref.blocked_count} 笔待人工核实`}
          </p>
          {/* GRW-060 合规：明确告知只有一级，不做分层返利 */}
          <p className="muted">
            规则：被邀请人完成首单后发放奖励（注册不发）；奖励仅一级，
            不存在多层级返利。
          </p>
        </div>
      )}
    </div>
  );
}
