// APP-072 App 侧提交职业资质（76 / 87 号 spec）。
//
// 探针：服务端有 12 个带「请…」指示的错误码，其中
//
//     certification_required → 「该类目需「{X}」职业资质，请提交证件影像并通过平台核验后接单」
//
// 而 `submitCertification` / `myCertifications` **只有网页有**。
// 受限类目的单，App 执行方会被挡下来，然后被告知去做一件**他的设备上做不到**的事。
// 这正是 V91 APP-066、V96 REMEDY_UI 立过的那条教训，只是这次漏在了闸门之外：
// 那张补救表是**手列的**，只覆盖了 4 条，这一条从来没被问过「谁来做」。
//
// 谁受影响：App 的主要用户是线下执行方（保洁、维修、搬家）。受限类目恰恰是
// 需要证的那些（电工、家电维修）。**接不了单就是赚不到钱**，而他没有电脑。
//
// 顺带说明一件事：`app.json` 里早就声明了相机与相册权限，
// 文案写着「用于拍摄任务交付凭证与到场照片」——**声明了权限，功能从未实现**。
// 这一批把那两行声明变成真的。
//
// 为什么这里可以上一个没在真机上验过的原生依赖，而 `captcha_required`
// 当初选择「如实记成缺口」（APP-071）：**两者的失败模式不同**。
// 验证码控件挂在登录路径上，装了而用不了就是把人**锁在账号外面**；
// 相册/相机挂在一个新增入口上，万一真机上打不开，用户退回到的正是
// 今天的状态（App 上交不了资质）——**坏的失败模式不会比现状更坏**。
// 而且这是 Expo 自家的托管模块、调用面只有「权限→选图→base64」三步，
// 集成逻辑（选图→上传→拿 ref→提交）在 jest 里是真测了的。
// 真机未验这件事记在 72 号台账（APP-073），不假装它已经验过。
import {
  apiErrorText,
  type CertificationApplicationView, type PlatformClient,
} from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

/** 服务端 2MB 上限（`storage.MAX_BYTES`）。本地先拦一道：
 *  手机多半在移动数据上，让他把 3MB 传完再被服务端拒绝是在花他的流量。
 *  服务端那道判断仍然是权威的，这里只是早一点、便宜一点。 */
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

const STATUS_LABEL: Record<string, string> = {
  pending: '待核验',
  approved: '已核准',
  rejected: '未通过',
  revoked: '已撤销',
};

export function CertificationsScreen({ client }: { client: PlatformClient }) {
  const [active, setActive] = useState<string[]>([]);
  const [rows, setRows] = useState<CertificationApplicationView[]>([]);
  const [name, setName] = useState('');
  const [holderName, setHolderName] = useState('');
  const [certNumber, setCertNumber] = useState('');
  const [issuer, setIssuer] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const r = await client.myCertifications().catch(() => null);
    setActive(r?.active ?? []);
    setRows(r?.applications ?? []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function pick(fromCamera: boolean) {
    setError(''); setNotice(''); setBusy(true);
    try {
      const perm = fromCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm.status !== 'granted') {
        // 「没反应」是最糟的失败：用户会反复点同一个按钮。
        setError(fromCamera ? '没有相机权限，请在系统设置里允许后重试'
                            : '没有相册权限，请在系统设置里允许后重试');
        return;
      }
      const opts = { quality: 0.5, base64: true } as const;
      const r = fromCamera
        ? await ImagePicker.launchCameraAsync(opts)
        : await ImagePicker.launchImageLibraryAsync(opts);
      if (r.canceled) return;
      const asset = r.assets?.[0];
      if (!asset?.base64) {
        setError('读不到图片数据，请换一张或改用拍照');
        return;
      }
      // base64 每 4 个字符约 3 字节
      if ((asset.base64.length / 4) * 3 > MAX_IMAGE_BYTES) {
        setError('这张图超过 2MB，请拍得近一些或选一张更小的');
        return;
      }
      // 资质要的是**文件名**（服务端据此发鉴权 URL 给审核员），
      // 不是可匿名访问的地址——证件影像不该有一条谁都能打开的链接（37 号 spec）。
      const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
      setImages((prev) => [...prev, up.ref]);
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setError(''); setNotice(''); setBusy(true);
    try {
      await client.submitCertification({
        name, holderName, certNumber,
        issuer: issuer || undefined,
        expiresAt: expiresAt.trim() || null,
        images,
      });
      setNotice('已提交，等待平台核验');
      setName(''); setHolderName(''); setCertNumber(''); setIssuer('');
      setExpiresAt(''); setImages([]);
      await load();
    } catch (e) {
      // 服务端的驳回原文直接显示：holder_mismatch / images_required / certificate_expired
      // 都带着一句能照着做的话，而客户端重写一遍只会和服务端慢慢对不上
      //（UI-075：第二份实现必然抄漏）。
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ gap: 12 }}>
      <Text style={s.muted}>
        {active.length ? `已核准：${active.join('、')}` : '还没有已核准的职业资质'}
      </Text>

      {rows.map((r) => (
        <View key={r.id} style={s.card}>
          <Text style={s.cardTitle}>{r.name} · {STATUS_LABEL[r.status] ?? r.status}</Text>
          {/* 被驳回而看不到原因，用户只能反复提交同一份材料——
              而每一次重提都要再等一轮人工核验。 */}
          {!!r.decision_reason && <Text style={s.muted}>平台意见：{r.decision_reason}</Text>}
          {!!r.expires_at && <Text style={s.muted}>有效期至 {r.expires_at.slice(0, 10)}</Text>}
        </View>
      ))}

      <Text style={s.cardTitle}>提交新的资质</Text>
      <TextInput style={s.input} value={name} onChangeText={setName}
                 placeholder="资质名称（如：电工 / 家电维修）" />
      {/* 服务端把证件姓名与实名严格比对（CERT-003：一张别人的电工证也是一张真证件）。
          这里不预填：`me` 刻意不返回实名姓名（最小必要），所以只能把规则说清楚。 */}
      <TextInput style={s.input} value={holderName} onChangeText={setHolderName}
                 placeholder="证件上的姓名（须与实名一致）" />
      <TextInput style={s.input} value={certNumber} onChangeText={setCertNumber}
                 placeholder="证件编号" />
      <TextInput style={s.input} value={issuer} onChangeText={setIssuer}
                 placeholder="发证机构（可不填）" />
      {/* CERT-005「发了就永久有效」是错的，而**有效期只能由申请人填**：
          `decide()` 不会补这个字段。所以这一栏不填就等于**提交一张永不过期的证**——
          第一版我把它硬写成 null，那等于悄悄给 App 用户开了个后门，
          让网页提交的证会过期、App 提交的永远有效。
          这里不引第二个原生依赖做日期选择器，手填 `YYYY-MM-DD` 就够，
          服务端把朴素时间按 UTC 处理（TZ-060）。 */}
      <TextInput style={s.input} value={expiresAt} onChangeText={setExpiresAt}
                 placeholder="有效期至 YYYY-MM-DD（证件上没有有效期才留空）" />

      <View style={{ flexDirection: 'row', gap: 12 }}>
        <TouchableOpacity disabled={busy} onPress={() => void pick(true)}>
          <Text style={s.link}>拍摄证件</Text>
        </TouchableOpacity>
        <TouchableOpacity disabled={busy} onPress={() => void pick(false)}>
          <Text style={s.link}>从相册选择</Text>
        </TouchableOpacity>
      </View>
      <Text style={s.muted}>
        {images.length ? `已附 ${images.length} 张证件影像` : '还没有附影像——没有影像，审核员看不到任何东西'}
      </Text>

      <Button title={busy ? '处理中…' : '提交核验'} disabled={busy} onPress={() => void submit()} />
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
  link: { color: '#2f6fed', paddingVertical: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
});
