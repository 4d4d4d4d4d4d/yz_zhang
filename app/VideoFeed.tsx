// CNT-014 / PRLX-042 App 侧视频沉浸流：上下滑、倍速、断点续播、流量提醒。
//
// 这个场景最容易做错、而且错了最致命的一条是：**同时播多个**。
// 每个解码中的视频都占一份硬件解码器与几十 MB 内存，滑过十条就能把
// 中低端机打到 OOM 或直接黑屏。所以下面所有设计都围绕一件事——
// **任何时刻有且只有一个 <Video> 在播**。
//
// 其余三条与 Web 版（web/src/VideoFeed.tsx）是同一套判断，但实现完全不同：
//
// - **流量提醒**：Web 用 `navigator.connection`，RN 没有这个 API，
//   用 `expo-network` 的 `getNetworkStateAsync()`。判断标准一致：
//   **取不到网络类型时按「可能是流量」处理**——这条的代价是用户的钱，
//   所以往保守一侧倒（与视差的 reduce-motion 相反，那条代价只是少点效果）。
// - **断点续播**：Web 用 localStorage，RN 用 AsyncStorage。语义一致：
//   这是「每个人自己的观看进度」，存本地不存服务端，也不跟着账号跨设备。
// - **自动播放受「减弱动态效果」影响**：自动播放的运动画面对前庭敏感人群
//   同样是诱因，WCAG 也要求自动播放可关闭。开了系统开关就**不自动播**，
//   与 Discover 的视差用同一个信号源。
import { Audio, ResizeMode, Video } from 'expo-av';
import * as Network from 'expo-network';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo, ActivityIndicator, Dimensions, FlatList,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import type { ContentItem, PlatformClient } from '@platform/core';

const { height: SCREEN_H, width: SCREEN_W } = Dimensions.get('window');
const RATES = [1, 1.25, 1.5, 2];
const POSITION_PREFIX = 'video-pos:';
/** 快看完了就不记：下次该从头开始，而不是跳到最后两秒。 */
const MIN_RESUME_MS = 3000;

function videoUrl(c: ContentItem, baseUrl: string): string | null {
  const u = (c.media_urls ?? []).find((x) => /\.(mp4|mov|webm)$/i.test(x));
  if (!u) return null;
  return u.startsWith('http') ? u : baseUrl + u;
}

async function loadPosition(id: number): Promise<number> {
  try {
    const raw = await AsyncStorage.getItem(POSITION_PREFIX + id);
    return raw ? Number(raw) || 0 : 0;
  } catch {
    return 0;              // 存储不可用不该影响播放
  }
}
async function savePosition(id: number, ms: number) {
  try {
    if (ms < MIN_RESUME_MS) await AsyncStorage.removeItem(POSITION_PREFIX + id);
    else await AsyncStorage.setItem(POSITION_PREFIX + id, String(Math.floor(ms)));
  } catch { /* 同上 */ }
}

/** 取不到网络类型时返回 true（按「可能是流量」处理）。
 *  代价落在用户的钱上，所以往保守一侧倒。 */
async function onCellular(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();
    if (state.type === Network.NetworkStateType.WIFI) return false;
    if (state.type === Network.NetworkStateType.CELLULAR) return true;
    return true;
  } catch {
    return true;
  }
}

export function VideoFeedScreen({ client, baseUrl }: {
  client: PlatformClient;
  baseUrl: string;
}) {
  const [items, setItems] = useState<Array<ContentItem & { _url: string }>>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [rate, setRate] = useState(1);
  const [allowData, setAllowData] = useState<boolean | null>(null);   // null = 还在判断
  const [reduceMotion, setReduceMotion] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      // 沉浸流要出声：默认的 iOS 静音开关会让视频没声音，用户以为坏了
      try { await Audio.setAudioModeAsync({ playsInSilentModeIOS: true }); } catch { /* 忽略 */ }
      setAllowData(!(await onCellular()));
      try {
        const reduce = await AccessibilityInfo.isReduceMotionEnabled?.();
        setReduceMotion(!!reduce);
      } catch { /* 取不到按 false */ }
      try {
        const feed = await client.contentFeed('latest');
        setItems(feed
          .map((c) => ({ ...c, _url: videoUrl(c, baseUrl) as string }))
          .filter((c) => !!c._url));
      } catch { /* 列表留空 */ }
      setLoading(false);
    })();
  }, [client, baseUrl]);

  // 只有**完全占据屏幕**的那一条算 active。阈值太低会在滑动中途
  // 短暂判定两条都可见，于是两个视频同时起播——正是要避免的那个错误。
  const viewabilityConfig = useRef({ itemVisiblePercentThreshold: 90 }).current;
  const onViewableItemsChanged = useRef(({ viewableItems }: {
    viewableItems: Array<{ index: number | null }>;
  }) => {
    const first = viewableItems[0];
    if (first?.index != null) setActiveIndex(first.index);
  }).current;

  if (loading || allowData === null) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }
  if (items.length === 0) {
    return <View style={styles.center}><Text style={styles.muted}>还没有视频内容。</Text></View>;
  }

  return (
    <View style={styles.root}>
      <FlatList
        data={items}
        keyExtractor={(c) => String(c.id)}
        pagingEnabled                      // 一屏一条，滑动即翻页
        showsVerticalScrollIndicator={false}
        snapToInterval={SCREEN_H}
        decelerationRate="fast"
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={viewabilityConfig}
        // 视频比图片吃内存得多：只保留当前页附近，离屏的整棵子树都卸掉
        removeClippedSubviews
        windowSize={3}
        initialNumToRender={1}
        maxToRenderPerBatch={2}
        renderItem={({ item, index }) => (
          <VideoPage
            item={item}
            // **有且只有一个在播**：其余全部 shouldPlay={false}
            active={index === activeIndex}
            rate={rate}
            allowData={allowData}
            reduceMotion={reduceMotion}
            onAllowData={() => setAllowData(true)}
            onCycleRate={() => setRate(RATES[(RATES.indexOf(rate) + 1) % RATES.length])}
          />
        )}
      />
    </View>
  );
}

function VideoPage({ item, active, rate, allowData, reduceMotion, onAllowData, onCycleRate }: {
  item: ContentItem & { _url: string };
  active: boolean;
  rate: number;
  allowData: boolean;
  reduceMotion: boolean;
  onAllowData: () => void;
  onCycleRate: () => void;
}) {
  const ref = useRef<Video | null>(null);
  const [resumed, setResumed] = useState(false);
  // 开了「减弱动态效果」就不自动播——自动播放的运动画面对前庭敏感人群
  // 同样是诱因，WCAG 也要求自动播放可关闭
  const [manualPlay, setManualPlay] = useState(false);
  const shouldPlay = active && allowData && (!reduceMotion || manualPlay);

  // 进入这一页时恢复断点。只做一次，否则每次 status 更新都会往回跳。
  useEffect(() => {
    if (!active || resumed) return;
    void (async () => {
      const ms = await loadPosition(item.id);
      if (ms > 0) await ref.current?.setPositionAsync(ms).catch(() => undefined);
      setResumed(true);
    })();
  }, [active, resumed, item.id]);

  // 离开这一页时落盘，并**显式暂停**——依赖卸载来停播在快速滑动时不可靠
  useEffect(() => {
    if (active) return;
    void (async () => {
      const status = await ref.current?.getStatusAsync().catch(() => null);
      if (status && 'positionMillis' in status) await savePosition(item.id, status.positionMillis);
      await ref.current?.pauseAsync().catch(() => undefined);
    })();
  }, [active, item.id]);

  return (
    <View style={styles.page}>
      {!allowData ? (
        <View style={styles.overlay}>
          <Text style={styles.overlayTitle}>{item.title || item.body.slice(0, 20)}</Text>
          <Text style={styles.overlayText}>
            当前可能在使用蜂窝数据，视频会消耗较多流量。
          </Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={onAllowData}>
            <Text style={styles.primaryBtnText}>继续播放（使用流量）</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          <Video
            ref={ref}
            source={{ uri: item._url }}
            style={styles.video}
            resizeMode={ResizeMode.COVER}
            isLooping
            shouldPlay={shouldPlay}
            rate={rate}
            shouldCorrectPitch            // 倍速下不变调
            onPlaybackStatusUpdate={(s) => {
              if ('positionMillis' in s && s.isPlaying) void savePosition(item.id, s.positionMillis);
            }}
          />
          {reduceMotion && !manualPlay && (
            <View style={styles.overlay}>
              <Text style={styles.overlayText}>已按系统设置关闭自动播放</Text>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => setManualPlay(true)}>
                <Text style={styles.primaryBtnText}>播放</Text>
              </TouchableOpacity>
            </View>
          )}
        </>
      )}

      <View style={styles.meta}>
        <Text style={styles.metaTitle} numberOfLines={2}>
          {item.title || item.body.slice(0, 40)}
        </Text>
        <Text style={styles.metaAuthor}>@{item.author_nickname}</Text>
      </View>
      <TouchableOpacity style={styles.rateBtn} onPress={onCycleRate}>
        <Text style={styles.rateText}>{rate}×</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' },
  muted: { color: '#9ca3af' },
  page: { width: SCREEN_W, height: SCREEN_H, backgroundColor: '#000' },
  video: { ...StyleSheet.absoluteFillObject },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center', justifyContent: 'center', gap: 12, padding: 32,
    backgroundColor: 'rgba(0,0,0,0.75)',
  },
  overlayTitle: { color: '#fff', fontSize: 18, fontWeight: '700', textAlign: 'center' },
  overlayText: { color: '#d1d5db', textAlign: 'center' },
  primaryBtn: { backgroundColor: '#2f6fed', paddingHorizontal: 20, paddingVertical: 12, borderRadius: 24 },
  primaryBtnText: { color: '#fff', fontWeight: '700' },
  meta: { position: 'absolute', left: 16, right: 80, bottom: 48, gap: 4 },
  metaTitle: { color: '#fff', fontSize: 16, fontWeight: '700' },
  metaAuthor: { color: '#dbeafe' },
  rateBtn: {
    position: 'absolute', right: 16, bottom: 48,
    backgroundColor: 'rgba(255,255,255,0.18)', paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 18,
  },
  rateText: { color: '#fff', fontWeight: '700' },
});
