import { apiErrorText, formatDateTime, type ContentItem } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { BlogEditor } from '../BlogEditor';
import { VideoFeed } from '../VideoFeed';
import { ParallaxHero } from '../Motion';
import { useApp } from '../store';

export default function Community() {
  const { client } = useApp();
  const [scope, setScope] = useState<'latest' | 'following' | 'video'>('latest');
  const [items, setItems] = useState<ContentItem[]>([]);
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [openComments, setOpenComments] = useState<number | null>(null);
  const [comments, setComments] = useState<Array<{ id: number; author_nickname: string; body: string }>>([]);
  const [commentText, setCommentText] = useState('');

  const load = useCallback(async () => {
    setItems(await client.contentFeed(scope === 'video' ? 'latest' : scope));
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
      setError(apiErrorText(err));
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
      <ParallaxHero title="社区"
                    subtitle="接单经验、作品与踩过的坑，都在这里沉淀" />
      <div className="card">
        <h3>发动态</h3>
        <textarea rows={2} placeholder="分享接单经验、作品展示…" value={body} onChange={(e) => setBody(e.target.value)} />
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ marginTop: 8 }}>
          <button disabled={!body.trim()} onClick={() => void post()}>发布</button>
        </div>
      </div>
      {/* CNT-003 博客编辑器：Markdown 预览 + 草稿箱 + 插图 + 标签 */}
      <BlogEditor client={client} onPublished={() => void load()} />

      <div className="row">
        <button className={scope === 'latest' ? '' : 'ghost'} onClick={() => setScope('latest')}>最新</button>
        <button className={scope === 'following' ? '' : 'ghost'} onClick={() => setScope('following')}>关注</button>
        <button className={scope === 'video' ? '' : 'ghost'} onClick={() => setScope('video')}>视频</button>
      </div>

      {/* CNT-014 视频沉浸流：上下滑 / 倍速 / 断点续播 / 流量提醒 */}
      {scope === 'video' && (
        <VideoFeed items={items
          .filter((c) => (c.media_urls ?? []).some((u) => /\.(mp4|mov|webm)$/i.test(u)))
          .map((c) => ({
            id: c.id,
            url: (c.media_urls ?? []).find((u) => /\.(mp4|mov|webm)$/i.test(u)) as string,
            title: c.title || c.body.slice(0, 20),
            author: c.author_nickname,
          }))} />
      )}
      <div className="list">
        {items.length === 0 && <div className="card muted">{scope === 'following' ? '关注的人还没有动态' : '还没有内容'}</div>}
        {items.map((c) => (
          <div className="card" key={c.id}>
            <div className="row">
              <strong>{c.author_nickname}</strong>
              {c.kind === 'blog' && <span className="badge">博客</span>}
              {/* CNT-024 按钮有状态：此前永远写着「关注」，已关注的人点了没有任何变化，
                  也没法从流里取消关注。null = 自己的内容，不画按钮。 */}
              {c.author_followed_by_viewer !== null && (
                <button className="ghost" style={{ padding: '2px 10px' }}
                        aria-pressed={c.author_followed_by_viewer}
                        onClick={async () => {
                          try {
                            const r = c.author_followed_by_viewer
                              ? await client.unfollowUser(c.author_id)
                              : await client.followUser(c.author_id);
                            // 同一个作者在这一页可能有好几条——一起改，不重新拉整页
                            setItems((old) => old.map((x) => (x.author_id === c.author_id
                              ? { ...x, author_followed_by_viewer: r.following } : x)));
                          } catch (e) {
                            setError(apiErrorText(e));
                          }
                        }}>
                  {c.author_followed_by_viewer ? '已关注' : '关注'}
                </button>
              )}
              <span className="spacer muted" style={{ flex: 1, textAlign: 'right' }}>
                {formatDateTime(c.created_at)}
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
