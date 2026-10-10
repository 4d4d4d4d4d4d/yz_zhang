import { useState } from 'react';
import { Button, Linking, Text, View } from 'react-native';

/** A wallet-browser handoff, not an embedded wallet or custody of signing keys. */
export function ChainEntry({ agreement, reference }: { agreement?: string; reference?: string }) {
  const [error, setError] = useState('');
  const base = process.env.EXPO_PUBLIC_CHAIN_WEB_URL;
  return <View style={{ gap: 8, paddingVertical: 12 }}>
    <Text>链上协作使用独立代币托管，不计入平台钱包余额。</Text>
    <Button title="打开链上协作" disabled={!base} onPress={async () => {
      setError('');
      try {
        const url = new URL(base!);
        if (url.protocol !== 'https:' && !(__DEV__ && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) throw new Error('链上协作地址必须使用 HTTPS');
        if (url.username || url.password) throw new Error('链上协作地址无效');
        if (agreement) url.searchParams.set('agreement', agreement);
        if (reference) url.searchParams.set('reference', reference);
        await Linking.openURL(url.href);
      } catch (e) { setError(e instanceof Error ? e.message : '无法打开链上协作'); }
    }} />
    <Text>{base ? '签名操作请在钱包内置浏览器中打开该页面完成。App 不保存私钥。' : '当前环境尚未配置链上协作入口。'}</Text>
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}
