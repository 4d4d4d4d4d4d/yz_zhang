import { ApiError, type ContentItem } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

export default function Community() {
  const { client, me } = useApp();
  const [scope, setScope] = useState<'latest' | 'following'>('latest');
  const [items, setItems] = useState<ContentItem[]>([]);
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [openComments, setOpenComments] = useState<number | null>(null);
  const [comments, setComments] = useState<Array<{ id: number; author_nickname: string; body: string }>>([]);
  const [commentText, setCommentText] = useState('');

  const load = useCallback(async () => {
    setItems(await client.contentFeed(scope));
  }, [client, scope]);

  useEffect(() => { void load(); }, [load]);

  async function post() {
    setError('');
    try {
      await client.createContent({ body });
      setBody('');
      setScope('latest');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  async function toggleComments(id: number) {
    if (openComments === id) {
      setOpenComments(null);
      return;
    }
    setOpenComments(id);
    setComments(await client.contentComments(id));
  }

  return (
    <div className="page">
      <div className="card">
        <h3>发动态</h3>
        <textarea rows={2} placeholder="分享接单经验、作品展示…" value={body} onChange={(e) => setBody(e.target.value)} />
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ marginTop: 8 }}>
          <button disabled={!body.trim()} onClick={() => void post()}>发布</button>
        </div>
      </div>
      <div className="row">
        <button className={scope === 'latest' ? '' : 'ghost'} onClick={() => setScope('latest')}>最新</button>
        <button className={scope === 'following' ? '' : 'ghost'} onClick={() => setScope('following')}>关注</button>
      </div>
      <div className="list">
        {items.length === 0 && <div className="card muted">{scope === 'following' ? '关注的人还没有动态' : '还没有内容'}</div>}
        {items.map((c) => (
          <div className="card" key={c.id}>
            <div className="row">
              <strong>{c.author_nickname}</strong>
              {c.kind === 'blog' && <span className="badge">博客</span>}
              {c.author_id !== me?.id && (
                <button className="ghost" style={{ padding: '2px 10px' }}
                        onClick={async () => { await client.followUser(c.author_id); await load(); }}>
                  关注
                </button>
              )}
              <span className="spacer muted" style={{ flex: 1, textAlign: 'right' }}>
                {new Date(c.created_at).toLocaleString()}
              </span>
            </div>
            {c.title && <h3>{c.title}</h3>}
            <p style={{ margin: '8px 0', whiteSpace: 'pre-wrap' }}>{c.body}</p>
            {c.linked_category && <span className="badge ok">可约同款服务：{c.linked_category}</span>}
            <div className="row muted" style={{ marginTop: 8 }}>
              <a onClick={async () => {
                await client.likeContent(c.id);
                await load();
              }} style={{ cursor: 'pointer' }}>
                {c.liked_by_me ? '❤️' : '🤍'} {c.like_count}
              </a>
              <a onClick={() => void toggleComments(c.id)} style={{ cursor: 'pointer' }}>💬 {c.comment_count}</a>
            </div>
            {openComments === c.id && (
              <div style={{ marginTop: 8 }}>
                {comments.map((cm) => (
                  <p key={cm.id} className="muted"><strong>{cm.author_nickname}</strong>：{cm.body}</p>
                ))}
                <div className="row" style={{ marginTop: 6 }}>
                  <input className="grow" value={commentText} onChange={(e) => setCommentText(e.target.value)} placeholder="写评论…" />
                  <button onClick={async () => {
                    await client.commentContent(c.id, commentText);
                    setCommentText('');
                    setComments(await client.contentComments(c.id));
                    await load();
                  }}>评论</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
