// CNT-003 博客编辑器：Markdown + 实时预览 + 草稿箱 + 插图 + 标签。
//
// 原 spec 四件事都写着，而此前 `contents` 表连存图片的字段都没有，
// `status` 也只有 published/removed——插图、视频、草稿箱全都无从谈起。
//
// 预览走 `<Markdown>`，它把 Markdown 解析成 React 元素而**不是 HTML 字符串**：
// 博客正文是别人写的、所有人都会看，转 HTML 塞进 DOM 就是一个现成的
// 存储型 XSS。
import { ApiError, apiErrorText, type PlatformClient } from '@platform/core';
import { useEffect, useState } from 'react';
import { Markdown } from './Markdown';
import PhotoPicker from './PhotoPicker';

type Draft = {
  id: number | null;
  title: string;
  body: string;
  tags: string[];
  media_urls: string[];
};

const EMPTY: Draft = { id: null, title: '', body: '', tags: [], media_urls: [] };

export function BlogEditor({ client, onPublished }: {
  client: PlatformClient;
  onPublished?: (id: number) => void;
}) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [drafts, setDrafts] = useState<Array<{ id: number; title: string; created_at: string }>>([]);
  const [tagInput, setTagInput] = useState('');
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadDrafts = async () => {
    try { setDrafts(await client.myDrafts()); } catch { /* 未登录等，草稿箱留空 */ }
  };
  useEffect(() => { void loadDrafts(); }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await fn(); await loadDrafts(); }
    catch (err) { setError(apiErrorText(err)); }
    finally { setBusy(false); }
  };

  // 存草稿：第一次 create，之后 patch 同一条——否则每按一次就多一条草稿
  const saveDraft = () => run(async () => {
    if (draft.id === null) {
      const created = await client.createContent({
        kind: 'blog', title: draft.title, body: draft.body,
        tags: draft.tags, media_urls: draft.media_urls, publish: false,
      });
      setDraft({ ...draft, id: created.id });
    } else {
      await client.editContent(draft.id, {
        title: draft.title, body: draft.body,
        tags: draft.tags, media_urls: draft.media_urls,
      });
    }
  });

  const publish = () => run(async () => {
    let id = draft.id;
    if (id === null) {
      const created = await client.createContent({
        kind: 'blog', title: draft.title, body: draft.body,
        tags: draft.tags, media_urls: draft.media_urls, publish: false,
      });
      id = created.id;
    } else {
      await client.editContent(id, {
        title: draft.title, body: draft.body,
        tags: draft.tags, media_urls: draft.media_urls,
      });
    }
    // 先存后发：发布端点会**重跑机审**，草稿是随便改的，存草稿时审过不算数
    await client.publishContent(id);
    setDraft(EMPTY);
    onPublished?.(id);
  });

  return (
    <div className="card" style={{ display: 'grid', gap: 8 }}>
      <h3>写博客</h3>
      <input value={draft.title} placeholder="标题（博客必填）"
        onChange={(e) => setDraft({ ...draft, title: e.target.value })} />

      <div className="row">
        <button className="ghost" onClick={() => setPreview(!preview)}>
          {preview ? '继续编辑' : '预览'}
        </button>
        <span className="muted">支持 # 标题 / **粗体** / `代码` / - 列表 / &gt; 引用 / [链接]()</span>
      </div>

      {preview
        ? <div className="card"><Markdown text={draft.body} /></div>
        : <textarea rows={12} value={draft.body} placeholder="正文（Markdown）"
            onChange={(e) => setDraft({ ...draft, body: e.target.value })} />}

      {/* CNT-003「插图」：上传后把 URL 插进正文，作者能看见自己插了什么 */}
      <PhotoPicker urls={draft.media_urls}
        onChange={(urls) => setDraft({
          ...draft,
          media_urls: urls,
          body: urls.length > draft.media_urls.length
            ? `${draft.body}\n\n![](${urls[urls.length - 1]})`
            : draft.body,
        })} />

      <div className="row">
        <input value={tagInput} placeholder="标签（回车添加）"
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || !tagInput.trim()) return;
            e.preventDefault();
            if (!draft.tags.includes(tagInput.trim())) {
              setDraft({ ...draft, tags: [...draft.tags, tagInput.trim()] });
            }
            setTagInput('');
          }} />
        {draft.tags.map((t) => (
          <span key={t} className="badge" onClick={() =>
            setDraft({ ...draft, tags: draft.tags.filter((x) => x !== t) })}>{t} ×</span>
        ))}
      </div>

      <div className="row">
        <button className="ghost" disabled={busy || !draft.body.trim()} onClick={saveDraft}>
          {draft.id === null ? '存草稿' : '更新草稿'}
        </button>
        <button disabled={busy || !draft.title.trim() || !draft.body.trim()} onClick={publish}>
          发布
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      {drafts.length > 0 && (
        <div>
          <h4>草稿箱（{drafts.length}）</h4>
          {drafts.map((d) => (
            <div key={d.id} className="row">
              <button className="ghost" onClick={() => run(async () => {
                const full = await client.getContent(d.id);
                setDraft({
                  id: full.id, title: full.title, body: full.body,
                  tags: full.tags ?? [], media_urls: full.media_urls ?? [],
                });
              })}>{d.title || '（无标题）'}</button>
              <span className="muted">{d.created_at.slice(0, 10)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
