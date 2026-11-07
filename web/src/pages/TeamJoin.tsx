import { apiErrorText, fmtYuan, formatDateTime, type TeamInvitePreview } from '@platform/core';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApp } from '../store';

/** TEAM-066 点开团队邀请链接（147 号 spec）：先看清楚是哪个团队、谁邀请、加入后的月度额度，再自己决定加不加入。 */
export default function TeamJoin() {
  const { token = '' } = useParams();
  const { client } = useApp();
  const [p, setP] = useState<TeamInvitePreview | null>(null);
  const [error, setError] = useState('');
  const [joined, setJoined] = useState(false);
  useEffect(() => { client.teamInvitePreview(token).then(setP).catch((e) => setError(apiErrorText(e))); }, [client, token]);
  return (
    <div className="page">
      <div className="card" aria-label="团队邀请">
        <h3>团队邀请</h3>
        {error && <p className="error">{error}</p>}
        {p && (
          <>
            <p><strong>{p.inviter_nickname || '团队所有者'}</strong> 邀请你加入「{p.team_name}」，成为普通成员。</p>
            <p className="muted">加入后你每月最多可以花团队的 {fmtYuan(p.spend_limit_cents)}（超出要审批）；这条邀请 {formatDateTime(p.expires_at)} 前有效。</p>
            {joined || p.already_member ? (
              <p role="status">{joined ? '已加入。' : '你已经是这个团队的成员了。'} <Link to="/teams">去团队</Link></p>
            ) : (
              <button onClick={() => void client.acceptTeamInvite(token).then(() => setJoined(true)).catch((e) => setError(apiErrorText(e)))}>加入团队</button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
