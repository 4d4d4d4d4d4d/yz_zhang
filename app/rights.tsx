// APP-075 我的权益：代扣明细、单独同意、数据主体权利（87 / 29 / 52 号 spec）。
//
// 这三样都是**法定权利**，而它们此前只有网页有：
//
//     myTax         web=True  app=False     TAX-021 代扣明细
//     grantConsent  web=True  app=False     LAW-031 单独同意
//     revokeConsent web=True  app=False     LAW-031 撤回同意
//     exportMyData  web=True  app=False     LAW-032 数据可携
//
// 为什么这比「少个页面」重：**执行方主要在手机上**。代扣明细是他报个税、
// 对账、与平台核对收入的唯一凭据；撤回同意是《个人信息保护法》给他的权利，
// 而「只能去电脑上撤回」不是一种可行使的权利。
//
// 与 V113 的资质提交同一条规矩（66 号 spec）：平台有这个能力、而用户在他的
// 设备上够不到，等于没有。
import {
  apiErrorText, fmtYuan,
  type AgreementStatus, type PlatformClient, type SensitiveScope, type TaxSummary,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import {
  Button, Share, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';

export function RightsScreen({ client }: { client: PlatformClient }) {
  const [tax, setTax] = useState<TaxSummary | null>(null);
  const [agreements, setAgreements] = useState<AgreementStatus | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError('');
    // 两段各自成立：代扣明细读不到不该让同意项也看不见（反过来同理）。
    // 合成一次 Promise.all + 一个 catch 会让一侧的故障把另一侧一起带走。
    await Promise.all([
      client.myTax().then(setTax).catch((e) => setError(apiErrorText(e))),
      client.myAgreements().then(setAgreements).catch((e) => setError(apiErrorText(e))),
    ]);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function setConsent(scope: SensitiveScope, grant: boolean) {
    setBusy(true); setError(''); setNotice(''); setConfirming(null);
    try {
      const r = grant
        ? await client.grantConsent(scope.key)
        : await client.revokeConsent(scope.key);
      // 撤回的**实际生效项**由服务端给（`applied`）——客户端不自己罗列，
      // 否则平台改了联动范围而这句话还停在旧的说法上。
      setNotice(grant ? '已授权'
        : `已撤回：${(r as { applied?: string[] }).applied?.join('、') || '已生效'}`);
      await load();
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportData() {
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await client.exportMyData();
      // LAW-032 数据可携：手机上没有「下载到磁盘」这个动作，所以走系统分享——
      // 用户可以存进备忘录、发给自己的邮箱。**不新引一个文件系统依赖**：
      // 这是 react-native 自带的能力。
      //
      // 边界：分享的是文本，数据很大时系统可能截断。所以同时把条目数显示出来，
      // 用户看得见「这次导出包含多少类数据」，而不是只拿到一段不知完整与否的字符串。
      const text = JSON.stringify(data, null, 2);
      await Share.share({ message: text, title: '我的平台数据' });
      setNotice(`已发起导出：包含 ${Object.keys(data).length} 类数据`);
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ gap: 12 }}>
      {/* ---------- TAX-021 代扣明细 ---------- */}
      <Text style={s.cardTitle}>个税代扣明细</Text>
      {!tax && !error && <Text style={s.muted}>正在读取…</Text>}
      {tax && (
        <>
          {tax.yearly.length === 0 && (
            <Text style={s.muted}>还没有代扣记录。有收入并完成放款后会出现在这里。</Text>
          )}
          {tax.yearly.map((y) => (
            <View key={y.year} style={s.card}>
              <Text style={s.cardTitle}>{y.year} 年</Text>
              <Text style={s.muted}>
                收入 {fmtYuan(y.income_cents)} · 已代扣 {fmtYuan(y.withheld_cents)} · {y.count} 笔
              </Text>
            </View>
          ))}
          {/* 服务端的免责声明**原样显示**：平台出具的是代扣明细，
              不是税务机关的完税证明。客户端重写一遍迟早和服务端对不上，
              而这句话的法律含义不容改写（TAX-021）。 */}
          <Text style={s.muted}>{tax.disclaimer}</Text>
        </>
      )}

      {/* ---------- LAW-031 单独同意 ---------- */}
      <Text style={s.cardTitle}>单独同意项</Text>
      {agreements?.sensitive_scopes.map((scope) => (
        <View key={scope.key} style={s.card}>
          <Text style={s.cardTitle}>{scope.purpose}</Text>
          <Text style={s.muted}>
            {scope.granted ? '已授权' : '未授权'}
            {scope.granted_at ? ` · ${scope.granted_at.slice(0, 10)}` : ''}
          </Text>
          {/* 撤回后会失去什么，必须在他点撤回**之前**就在屏幕上
              （`revocation_effect` 的类型注释写着这条）。 */}
          {scope.granted && !!scope.revocation_effect && (
            <Text style={s.muted}>撤回后：{scope.revocation_effect}</Text>
          )}
          {!scope.revocable && scope.granted && (
            <Text style={s.muted}>这一项是履约必需，无法单独撤回。</Text>
          )}
          {confirming === scope.key ? (
            <View style={s.row}>
              {/* 两步确认：撤回会连带停掉实名与资金动作（LAW-031），
                  而手机上误触一下的代价是账号立刻不能接单、不能提现。 */}
              <Button title={busy ? '处理中…' : '确认撤回'} disabled={busy}
                      onPress={() => void setConsent(scope, false)} />
              <TouchableOpacity onPress={() => setConfirming(null)}>
                <Text style={s.link}>不撤回</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <Button
              title={scope.granted ? '撤回同意' : '授权'}
              disabled={busy || (scope.granted && !scope.revocable)}
              onPress={() => (scope.granted ? setConfirming(scope.key) : void setConsent(scope, true))}
            />
          )}
        </View>
      ))}

      {/* ---------- LAW-032 数据主体权利 ---------- */}
      <Text style={s.cardTitle}>我的数据权利</Text>
      {/* 服务端给的权利清单原样列出——「有能力但用户找不到」等于没有
          （`rights` 的类型注释写着这条）。 */}
      {Object.entries(agreements?.rights ?? {}).map(([key, text]) => (
        <Text key={key} style={s.muted}>· {text}</Text>
      ))}
      <Button title={busy ? '处理中…' : '导出我的数据'} disabled={busy}
              onPress={() => void exportData()} />

      {!!notice && <Text style={s.muted}>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  cardTitle: { fontSize: 16, fontWeight: '600' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#dc2626' },
  link: { color: '#2f6fed', paddingVertical: 8, paddingHorizontal: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
