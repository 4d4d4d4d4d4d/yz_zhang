// APP-074f（441 号 spec）内容：网页早就能发帖、存草稿、点赞、评论（web/src/pages/Community.tsx、BlogEditor.tsx），
// App 的内容流只能看、只能关注作者。只有手机的人在 App 上发不了动态，也回不了别人的评论——
// 个人门户（VISION V-1）的「作品与动态」一半是空的。
//
// 规则都在服务端：发布与草稿的状态、点赞幂等（返回当前是否已赞和总数）、评论的审核与举报。
// App 只做两件事：把请求发对，把服务端说的理由原样说出来。
import { apiErrorText, asList, type ContentItem, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

/** 发动态与草稿：写一段话，发布或存草稿；草稿可以改了再发。 */
export function ComposeBlock({ client, onPublished }: { client: PlatformClient; onPublished?: () => void }) {
  const [body, setBody] = useState('');
  const [drafts, setDrafts] = useState<ContentItem[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadDrafts = useCallback(async () => {
    setDrafts(asList<ContentItem>(await client.myDrafts().catch(() => [])));
  }, [client]);
  useEffect(() => { void loadDrafts(); }, [loadDrafts]);

  async function act(fn: () => Promise<unknown>, done: string, published = false) {
    setError(''); setNotice('');
    try {
      await fn();
      setNotice(done);
      await loadDrafts();
      if (published) onPublished?.();
    } catch (e) {
      setError(apiErrorText(e));
    }
  }
  const text = body.trim();
  return (
    <View style={s.card}>
      <Text style={s.title}>{editing ? '改草稿' : '发动态'}</Text>
      <TextInput accessibilityLabel="动态内容" style={s.input} multiline placeholder="说说你在做什么…" value={body} onChangeText={setBody} />
      <View style={s.row}>
        {editing ? (
          <>
            <TouchableOpacity style={[s.primary, !text && s.disabled]} disabled={!text}
              onPress={() => void act(async () => { await client.editContent(editing, { body: text }); setEditing(null); setBody(''); }, '草稿已保存')}>
              <Text style={s.primaryText}>保存草稿</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { setEditing(null); setBody(''); }}><Text style={s.link}>取消</Text></TouchableOpacity>
          </>
        ) : (
          <>
            <TouchableOpacity style={[s.primary, !text && s.disabled]} disabled={!text}
              onPress={() => void act(async () => { await client.createContent({ body: text }); setBody(''); }, '已发布', true)}>
              <Text style={s.primaryText}>发布</Text>
            </TouchableOpacity>
            <TouchableOpacity disabled={!text}
              onPress={() => void act(async () => { await client.createContent({ body: text, publish: false }); setBody(''); }, '已存为草稿')}>
              <Text style={[s.link, !text && s.disabled]}>存草稿</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
      {!!notice && <Text style={s.muted}>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {drafts.length > 0 && (
        <View style={{ gap: 4 }}>
          <Text style={s.muted}>我的草稿（{drafts.length}）</Text>
          {drafts.map((d) => (
            <View key={d.id} style={s.row}>
              <Text style={{ flex: 1 }} numberOfLines={1}>{d.title || d.body}</Text>
              <TouchableOpacity onPress={() => { setEditing(d.id); setBody(d.body); }}><Text style={s.link}>改</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => void act(() => client.publishContent(d.id), '草稿已发布', true)}>
                <Text style={s.link}>发布</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

type Comment = { id: number; author_nickname: string; body: string };

/** 一条内容下面的点赞与评论。点赞以服务端返回的为准（幂等、带总数）；评论展开时才去拉。 */
export function ContentActions({ client, item }: { client: PlatformClient; item: ContentItem }) {
  const [liked, setLiked] = useState(!!item.liked_by_me);
  const [likes, setLikes] = useState(Number(item.like_count) || 0);
  const [open, setOpen] = useState(false);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentCount, setCommentCount] = useState(Number(item.comment_count) || 0);
  const [text, setText] = useState('');
  const [error, setError] = useState('');

  async function loadComments() {
    setComments(asList<Comment>(await client.contentComments(item.id).catch(() => [])));
  }
  return (
    <View style={{ gap: 6 }}>
      <View style={s.row}>
        <TouchableOpacity accessibilityRole="button" accessibilityState={{ selected: liked }} onPress={async () => {
          setError('');
          try {
            const r = await client.likeContent(item.id);
            setLiked(!!r.liked);
            setLikes(Number(r.like_count) || 0);
          } catch (e) {
            setError(apiErrorText(e));
          }
        }}>
          <Text style={s.link}>{liked ? '已赞' : '赞'} {likes}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => { const next = !open; setOpen(next); if (next) void loadComments(); }}>
          <Text style={s.link}>{open ? '收起评论' : `评论 ${commentCount}`}</Text>
        </TouchableOpacity>
      </View>
      {open && (
        <View style={{ gap: 4 }}>
          {comments.length === 0 && <Text style={s.muted}>还没有评论</Text>}
          {comments.map((c) => (
            <Text key={c.id}><Text style={{ fontWeight: '600' }}>{c.author_nickname}</Text>：{c.body}</Text>
          ))}
          <View style={s.row}>
            <TextInput accessibilityLabel="写评论" style={[s.input, { flex: 1 }]} placeholder="写评论…" value={text} onChangeText={setText} />
            <TouchableOpacity disabled={!text.trim()} onPress={async () => {
              setError('');
              try {
                await client.commentContent(item.id, text.trim());
                setText('');
                setCommentCount((n) => n + 1);
                await loadComments();
              } catch (e) {
                setError(apiErrorText(e));
              }
            }}>
              <Text style={[s.link, !text.trim() && s.disabled]}>发送</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 14, marginHorizontal: 12, marginBottom: 14, padding: 14, gap: 8 },
  title: { fontSize: 15, fontWeight: '600' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  primary: { backgroundColor: '#275c52', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 16 },
  primaryText: { color: '#fff', fontWeight: '600' },
  link: { color: '#275c52', fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 12 },
  disabled: { opacity: 0.4 },
  error: { color: '#dc2626' },
});
