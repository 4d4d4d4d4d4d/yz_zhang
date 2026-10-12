import { apiErrorText, formatDate, type KnowledgeCluster, type KnowledgeClusterDetail, type KnowledgeClusterList, type KnowledgeOutcome } from '@platform/core';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ClusterUnits } from '../ExperienceUnits';
import { useApp } from '../store';

type Ask = Awaited<ReturnType<ReturnType<typeof useApp>['client']['legalAsk']>>;
type Card = Awaited<ReturnType<ReturnType<typeof useApp>['client']['knowledgeCards']>>[number];
type Hits = Awaited<ReturnType<ReturnType<typeof useApp>['client']['knowledgeSearch']>>;

const fmtYuan = (cents: number) => `¥${(cents / 100).toFixed(2)}`;

/** LAW-051 / KB-023 「不懂就问」（97 号 spec）。
 *
 * 用户愿景里的两条——「AI 协助不懂领域解决」与「平台能够累积成功经验」——
 * 服务端都是真的，而**两端一个入口都没有**：`legalAsk` / `knowledgeCards` /
 * `knowledgeSearch` 三个方法 web、App、运营台三端零调用。
 *
 * 平台一边在攒经验（一笔闭环就落一张卡），一边没有任何人读得回去。
 */
export default function Ask() {
  return (
    <div className="page">
      <LegalAsk />
      <Subclasses />
      <Experience />
    </div>
  );
}

function LegalAsk() {
  const { client } = useApp();
  const [q, setQ] = useState('');
  const [res, setRes] = useState<Ask | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (!q.trim()) return;
    setBusy(true); setErr('');
    try {
      setRes(await client.legalAsk(q));
    } catch (e) {
      setErr(apiErrorText(e));
      setRes(null);
    } finally {
      setBusy(false);
    }
  }

  // LAW-051 三种结局不是三种措辞，是三件不同的事。
  // 都画成一段灰字的后果：把一条安全升级通道说成「机器人没答上来」。
  const high = res?.refused_reason === 'high_risk';
  const out = res?.refused_reason === 'out_of_scope';

  return (
    <div className="card">
      <h3>问平台：法律与规则</h3>
      <p className="muted">
        可以问：合约有没有效力 / 对方拖欠怎么办 / 算不算劳动关系 / 个人信息怎么删
      </p>
      <div className="row" style={{ marginTop: 8 }}>
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && void ask()}
               placeholder="描述你的问题…" aria-label="法律问题" />
        <button disabled={busy} onClick={() => void ask()}>{busy ? '正在查…' : '提问'}</button>
      </div>

      {err && <p className="error" role="alert">{err}</p>}

      {res && (
        <div style={{ marginTop: 12 }}>
          {high ? (
            // 人身安全：不是「答不了」，是**现在就该去别处**。
            // 这一支刻意不给平台内的任何按钮——服务端的 remedy 也是 null。
            <div className="card" role="alert">
              <strong>这个问题平台不作解答</strong>
              <p>{res.answer}</p>
              <p className="muted">如正在发生危险，请直接拨打 110；平台的任何流程都不优先于此。</p>
            </div>
          ) : out ? (
            <div className="card" role="status">
              <strong>平台知识库答不了这一条</strong>
              <p>{res.answer}</p>
              {/* 66 号 spec：服务端说「去发一单法律咨询」，这里就得真的送得到。
                  类目用服务端给的，不在前端写死——类目改名时写死的那个会把人
                  送到一个空的下拉框前面。 */}
              {res.remedy?.action === 'publish_task' && res.remedy.category && (
                <Link className="button-link" to={`/publish?category=${encodeURIComponent(res.remedy.category)}`}>
                  {res.remedy.label}
                </Link>
              )}
            </div>
          ) : (
            <div className="card" role="status">
              <p>{res.answer}</p>
            </div>
          )}
          {/* 原样展示：平台给的是一般性法律信息，不是法律意见。这句话的
              法律含义不容客户端改写（与 V119 的代扣免责声明同一条规矩）。 */}
          <p className="muted" style={{ marginTop: 8 }}>{res.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

const OUTCOME_LABEL: Record<KnowledgeOutcome, string> = { completed: '完成', disputed: '有纠纷', cancelled: '取消' };

/** KB-073/074 按子类看经验（108 号 spec）：这一类活儿通常怎么做、通常多少钱。
 *  子类是结论，样本是证据——每个结论都带样本量与时间范围；样本太少的不给价。 */
function Subclasses() {
  const { client } = useApp();
  const [list, setList] = useState<KnowledgeClusterList | null>(null);
  const [detail, setDetail] = useState<KnowledgeClusterDetail | null>(null);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');

  async function load() {
    setErr('');
    setDetail(null);
    try {
      setList(await client.knowledgeClusters(undefined, q.trim()));
    } catch (e) {
      setErr(apiErrorText(e));
    }
  }

  return (
    <div className="card">
      <h3>这一类活儿通常怎么做、通常多少钱</h3>
      <p className="muted">平台把相似的闭环经验归成子类：每一类给价格与工期的分布、完成与纠纷的比例、
        多数人的做法，以及少数但同样做成了的做法。</p>
      <div className="row" style={{ marginTop: 8 }}>
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && void load()}
               placeholder="想做什么？例如：同城代取快递" aria-label="搜子类" />
        <button onClick={() => void load()}>按子类看</button>
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      {list && !list.semantic && list.items.length > 0 && (
        <p className="muted" role="status">当前不是语义检索（{list.model}）：排序只看字面相近。</p>
      )}
      {list && list.items.length === 0 && (
        <p className="muted">还没有子类。经验要先攒够、并由运营标定归并阈值之后，才会长出子类——这里是空的，不是出错了。</p>
      )}
      {list && list.items.length > 0 && !detail && (
        <ul className="list" style={{ marginTop: 8 }}>
          {list.items.map((c) => (
            <li key={c.id} className="task-item">
              <button className="ghost" onClick={async () => {
                try { setDetail(await client.knowledgeCluster(c.id)); } catch (e) { setErr(apiErrorText(e)); }
              }}>{c.label}</button>
              <ClusterStats c={c} />
            </li>
          ))}
        </ul>
      )}
      {detail && (
        <div style={{ marginTop: 8 }}>
          <button className="ghost" onClick={() => setDetail(null)}>← 返回子类列表</button>
          <h4>{detail.label}</h4>
          <ClusterStats c={detail} />
          {detail.consensus_steps.length > 0 && (
            <>
              <p><strong>多数人的做法</strong>（{detail.steps_basis} 个有拆解的样本）：</p>
              <ol>{detail.consensus_steps.map((s) => <li key={s.title}>{s.title} <em className="muted">{s.count} 次</em></li>)}</ol>
            </>
          )}
          {(detail.dissent.length > 0 || detail.dissent_hidden > 0) && (
            <>
              {/* KB-072 分歧不许被平均掉：少数但同样做成了的做法单独列出 */}
              <p><strong>不一样、但同样做成了的做法</strong>：</p>
              <ul>{detail.dissent.map((d, i) => <li key={i}>{d.steps.join(' → ')} <em className="muted">{d.count} 次</em></li>)}</ul>
              {detail.dissent_hidden > 0 && (
                <p className="muted">另有 {detail.dissent_hidden} 种只出现过一次的做法（不展示内容，以免暴露个案）。</p>
              )}
            </>
          )}
          <p className="muted">{detail.evidence.note}</p>
          {/* KB-086 从这个子类蒸馏出来、可以直接拿去用的单元（109 号 spec） */}
          <ClusterUnits clusterId={detail.id} />
        </div>
      )}
    </div>
  );
}

function ClusterStats({ c }: { c: KnowledgeCluster }) {
  return (
    <span className="muted" data-cluster={c.id}>
      {c.sample_count} 个样本
      {!c.few_samples && c.price_p50_cents !== null && <> · 价格中位 {fmtYuan(c.price_p50_cents)}（90% 在 {fmtYuan(c.price_p90_cents ?? 0)} 以内）</>}
      {!c.few_samples && c.duration_p50_days !== null && <> · 工期中位 {c.duration_p50_days ? `${c.duration_p50_days} 天` : '当日'}</>}
      {' · '}{(Object.keys(OUTCOME_LABEL) as KnowledgeOutcome[]).map((o) => `${OUTCOME_LABEL[o]} ${c.outcome_mix[o] ?? 0}`).join(' / ')}
      {c.first_sample_at && <> · {formatDate(c.first_sample_at)} ~ {formatDate(c.last_sample_at ?? c.first_sample_at)}</>}
      {c.few_samples && <strong> · {c.note}</strong>}
    </span>
  );
}

/** KB-023 平台攒下来的经验，读回来。 */
function Experience() {
  const { client } = useApp();
  const [cards, setCards] = useState<Card[] | null>(null);
  const [hits, setHits] = useState<Hits | null>(null);
  const [q, setQ] = useState('');
  const [err, setErr] = useState('');
  const [loaded, setLoaded] = useState(false);

  async function load() {
    setErr('');
    try {
      setCards(await client.knowledgeCards());
    } catch (e) {
      setErr(apiErrorText(e));
    } finally {
      setLoaded(true);
    }
  }

  async function search() {
    if (!q.trim()) return;
    setErr('');
    try {
      setHits(await client.knowledgeSearch(q, 'card'));
    } catch (e) {
      setErr(apiErrorText(e));
    }
  }

  return (
    <div className="card">
      <h3>平台攒下来的经验</h3>
      <p className="muted">
        每一笔走完验收的合作都会沉淀一张脱敏经验卡：实际成交价、实际工期、结果如何。
      </p>
      <div className="row" style={{ marginTop: 8 }}>
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && void search()}
               placeholder="搜经验：保洁 / 跑腿 / 软件开发…" aria-label="搜索经验" />
        <button onClick={() => void search()}>检索</button>
        <button className="ghost" onClick={() => void load()}>看最近的</button>
      </div>

      {err && <p className="error" role="alert">{err}</p>}

      {hits && (
        <div style={{ marginTop: 12 }}>
          {/* KB-011 `semantic` / `degraded` 是服务端**有意暴露**的：
              缺省 embedding 是词袋哈希不是语义模型，没建索引时还会退化成
              词面命中。把它藏起来，等于把服务端那份诚实在最后一步扔掉——
              一个悄悄退化成关键词的「语义检索」比没有更糟：你不会去修它。 */}
          {!hits.semantic && (
            <p className="muted" role="status">
              当前检索<strong>不是语义检索</strong>（{hits.model}
              {hits.degraded ? '，且已退化为词面命中' : ''}）：
              换个说法可能就搜不到同一批经验。
            </p>
          )}
          {hits.results.length === 0
            ? <p className="muted">没有命中。平台只在合作走完验收后才沉淀经验，这类活儿可能还没有闭环样本。</p>
            : <ul>{hits.results.map((r) => (
                <li key={r.id}>{r.text}<em className="muted"> 相似度 {r.score.toFixed(2)}</em></li>
              ))}</ul>}
        </div>
      )}

      {cards && (
        <div style={{ marginTop: 12 }}>
          {cards.length === 0
            ? <p className="muted">还没有经验卡。平台只统计走完验收的合作，没有闭环就没有经验——这里是空的，不是出错了。</p>
            : <table><thead><tr>
                <th>类目</th><th>城市</th><th>实际成交</th><th>工期</th><th>结果</th>
              </tr></thead><tbody>
                {cards.map((c) => (
                  <tr key={c.id}>
                    <td>{c.category}{c.has_decomposition && <em className="muted"> 含分解</em>}</td>
                    <td>{c.city || '—'}</td>
                    <td>{fmtYuan(c.price_actual_cents)}</td>
                    <td>{c.duration_days ? `${c.duration_days} 天` : '当日'}</td>
                    {/* KB-004 失败与纠纷案例**同样入库**，所以这一列必须显示出来：
                        把 disputed 的卡和 completed 的混在一起当「行情」看，
                        得到的参考价偏高。 */}
                    <td>{{ completed: '已完成', disputed: '有纠纷', cancelled: '已取消' }[c.outcome] ?? c.outcome}</td>
                  </tr>
                ))}
              </tbody></table>}
        </div>
      )}
      {!cards && !hits && loaded && !err && <p className="muted">点「看最近的」。</p>}
    </div>
  );
}
