// APP-092 App 屏幕错误边界（183 号 spec）：一屏渲染出错时只坏这一屏，顶栏与底部 Tab 还在，告诉人为什么、怎么办。
//
// RN 里渲染错误会把整棵树卸掉（生产包里是白屏或闪退回桌面）。按屏加边界后：顶栏还在、这一屏换成说明，
// 点「返回」回到上一层；换一屏（key 变了）边界自动复位。
import { Component, type ReactNode } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

type Props = { children: ReactNode; onBack: () => void };

export class ScreenBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    // 只记错误类型，不记内容：屏幕上的数据可能有个人信息（SEC-065）
    console.error('screen_render_failed', error instanceof Error ? error.name : 'unknown');
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <View style={styles.card} accessibilityRole="alert" accessibilityLabel="这一页没加载出来">
        <Text style={styles.title}>这一页没加载出来</Text>
        <Text style={styles.muted}>可能是网络或服务暂时不正常。返回再进来试试；一直这样，请在「我的空间 → 客服」提单，写上是哪一页。</Text>
        <TouchableOpacity onPress={this.props.onBack}><Text style={styles.link}>← 返回</Text></TouchableOpacity>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 8, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  link: { color: '#275c52' },
});
