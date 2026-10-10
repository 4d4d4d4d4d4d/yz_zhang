// APP-078 不懂就问：法律问答与平台攒下来的经验（97 号 spec）。
//
// 用户复述的六条愿景里有两条是关于「平台知道什么」的：
// 「AI 协助不懂领域解决」与「平台能够累积成功经验」。量过之后两条都是
// 同一种状态——**服务端是真的，而没有任何客户端够得到**：
//
//     legalAsk        web=False  app=False  admin=False
//     knowledgeCards  web=False  app=False  admin=False
//     knowledgeSearch web=False  app=False  admin=False
//
// 跑一笔闭环就能看见平台确实在攒：`/knowledge/cards` 立刻多一张卡。
// 也就是说平台一边攒经验，一边没有人读得回去。
//
// 这一页在手机上尤其要紧：问「这事我不懂，该怎么办」的那一刻，
// 人很少坐在电脑前。
import {
  apiErrorText, fmtYuan, type PlatformClient,
} from '@platform/core';
import { useCallback, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

type AskResult = Awaited<ReturnType<PlatformClient['legalAsk']>>;
type Card = Awaited<ReturnType<PlatformClient['knowledgeCards']>>[number];
type Hits = Awaited<ReturnType<PlatformClient['knowledgeSearch']>>;

const OUTCOME_LABEL: Record<string, string> = {
  completed: '已完成', disputed: '有纠纷', cancelled: '已取消',
};

export function AskScreen({ client, onPublish }: {
  client: PlatformClient;
  /** 问答答不了时，把人送去发一单法律咨询（服务端给的类目）。 */
  onPublish?: (category: string) => void;
}) {
  const [q, setQ] = useState('');
  const [res, setRes] = useState<AskResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const ask = useCallback(async () => {
    if (!q.trim()) return;
    setBusy(true); setError('');
    try {
      setRes(await client.legalAsk(q));
    } catch (e) {
      setError(apiErrorText(e));
      setRes(null);
    } finally {
      setBusy(false);
    }
  }, [client, q]);

  // LAW-051 三种结局是三件不同的事，不是三种措辞。
  // 服务端此前只用 `refused: bool` 区分，于是「请立即拨打 110」与
  // 「这个得找律师」在客户端眼里一模一样——本批给服务端补了 `refused_reason`。
  const high = res?.refused_reason === 'high_risk';
  const out = res?.refused_reason === 'out_of_scope';

  return (
    <View style={{ gap: 12 }}>
      <View style={styles.card}>
        <Text style={styles.title}>问平台：法律与规则</Text>
        <Text style={styles.muted}>
          可以问：合约有没有效力 / 对方拖欠怎么办 / 算不算劳动关系 / 个人信息怎么删
        </Text>
        <TextInput style={styles.input} value={q} onChangeText={setQ}
                   placeholder="描述你的问题…" multiline />
        <Button title={busy ? '正在查…' : '提问'} onPress={() => void ask()} disabled={busy} />
        {!!error && <Text style={styles.error}>{error}</Text>}

        {res && high && (
          // 人身安全这一支**不给平台内的任何按钮**——服务端的 remedy 也是 null。
          // 在它旁边摆一个「发布咨询任务」，是把紧急情况降级成一笔生意。
          <View style={styles.alert}>
            <Text style={styles.alertTitle}>这个问题平台不作解答</Text>
            <Text>{res.answer}</Text>
            <Text style={styles.muted}>
              如正在发生危险，请直接拨打 110；平台的任何流程都不优先于此。
            </Text>
          </View>
        )}
        {res && out && (
          <View style={styles.answer}>
            <Text style={styles.alertTitle}>平台知识库答不了这一条</Text>
            <Text>{res.answer}</Text>
            {/* 66 号 spec：服务端说「去发一单法律咨询」，这里就得真的送得到。
                类目用服务端给的，不在客户端写死——类目改名时写死的那个会把人
                送到一个不存在的类目去，而且是静默的。 */}
            {res.remedy?.action === 'publish_task' && !!res.remedy.category && onPublish && (
              <Button title={res.remedy.label}
                      onPress={() => onPublish(res.remedy!.category)} />
            )}
          </View>
        )}
        {res && !high && !out && (
          <View style={styles.answer}><Text>{res.answer}</Text></View>
        )}
        {/* 原样展示：平台给的是一般性法律信息，不是法律意见。
            这句话的法律含义不容客户端改写（与 V119 的代扣免责声明同一条规矩）。 */}
        {res && <Text style={styles.muted}>{res.disclaimer}</Text>}
      </View>

      <ExperienceBlock client={client} />
    </View>
  );
}

/** KB-023 平台攒下来的经验，读回来。 */
export function ExperienceBlock({ client }: { client: PlatformClient }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [hits, setHits] = useState<Hits | null>(null);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      setCards(await client.knowledgeCards());
    } catch (e) {
      setError(apiErrorText(e));
    }
  }, [client]);

  const search = useCallback(async () => {
    if (!q.trim()) return;
    setError('');
    try {
      setHits(await client.knowledgeSearch(q, 'card'));
    } catch (e) {
      setError(apiErrorText(e));
    }
  }, [client, q]);

  return (
    <View style={styles.card}>
      <Text style={styles.title}>平台攒下来的经验</Text>
      <Text style={styles.muted}>
        每一笔走完验收的合作都会沉淀一张脱敏经验卡：实际成交价、实际工期、结果如何。
      </Text>
      <TextInput style={styles.input} value={q} onChangeText={setQ}
                 placeholder="搜经验：保洁 / 跑腿 / 软件开发…" />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button title="检索" onPress={() => void search()} />
        <Button title="看最近的" onPress={() => void load()} />
      </View>
      {!!error && <Text style={styles.error}>{error}</Text>}

      {hits && (
        <View style={{ gap: 4, marginTop: 8 }}>
          {/* KB-011 `semantic` / `degraded` 是服务端**有意暴露**的：缺省
              embedding 是词袋哈希不是语义模型，没建索引时还会退化成词面命中。
              把它藏起来等于把服务端那份诚实在最后一步扔掉——一个悄悄退化成
              关键词的「语义检索」比没有更糟：你不会去修它。 */}
          {!hits.semantic && (
            <Text style={styles.muted}>
              当前检索不是语义检索（{hits.model}
              {hits.degraded ? '，且已退化为词面命中' : ''}）：换个说法可能就搜不到同一批经验。
            </Text>
          )}
          {hits.results.length === 0
            ? <Text style={styles.muted}>
                没有命中。平台只在合作走完验收后才沉淀经验，这类活儿可能还没有闭环样本。
              </Text>
            : hits.results.map((r) => (
                <Text key={r.id}>{r.text}  <Text style={styles.muted}>相似度 {r.score.toFixed(2)}</Text></Text>
              ))}
        </View>
      )}

      {cards && (
        <View style={{ gap: 6, marginTop: 8 }}>
          {cards.length === 0
            ? <Text style={styles.muted}>
                还没有经验卡。平台只统计走完验收的合作，没有闭环就没有经验——
                这里是空的，不是出错了。
              </Text>
            : cards.map((c) => (
                <View key={c.id} style={styles.row}>
                  <Text style={styles.rowTitle}>
                    {c.category}{c.city ? ` · ${c.city}` : ''}
                    {c.has_decomposition ? ' · 含分解' : ''}
                  </Text>
                  {/* KB-004 失败与纠纷案例**同样入库**，所以结果必须显示：
                      把 disputed 的卡与 completed 的混在一起当行情看，参考价偏高。 */}
                  <Text style={styles.muted}>
                    实际成交 {fmtYuan(c.price_actual_cents)} ·
                    {c.duration_days ? ` ${c.duration_days} 天` : ' 当日'} ·
                    {' '}{OUTCOME_LABEL[c.outcome] ?? c.outcome}
                  </Text>
                </View>
              ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff', borderRadius: 18, padding: 20, gap: 10,
    borderWidth: 1, borderColor: '#dce5de',
  },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
  input: {
    backgroundColor: '#fff', borderRadius: 8, padding: 12,
    borderWidth: 1, borderColor: '#e5e7eb',
  },
  answer: {
    backgroundColor: '#f6f8f6', borderRadius: 12, padding: 14, gap: 6,
    borderWidth: 1, borderColor: '#dce5de',
  },
  alert: {
    backgroundColor: '#fef2f2', borderRadius: 12, padding: 14, gap: 6,
    borderWidth: 1, borderColor: '#fecaca',
  },
  alertTitle: { fontWeight: '600' },
  row: { gap: 2 },
  rowTitle: { fontWeight: '600' },
});
