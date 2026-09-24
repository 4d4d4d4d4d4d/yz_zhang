// APP-002 / CNT-011/014 发现流：视差滚动（parallax）。
//
// 视差的做法是：背景层随滚动**慢于**前景移动，产生depth。实现上有三个
// 非做不可的约束，每一条都不是"优化"而是"不这样做就是坏的"：
//
// ① **必须走 native driver。** RN 的 Animated 默认在 JS 线程算每一帧，
//    滚动时 JS 线程本来就忙，视差会肉眼可见地掉帧、跟手感发飘。
//    `useNativeDriver: true` 把动画搬到 UI 线程——代价是**只能动
//    transform 与 opacity**（不能动 height/top/backgroundColor）。
//    所以下面所有视差都只用 translateY / scale / opacity。
//
// ② **必须尊重「减弱动态效果」。** iOS 与 Android 都有这个系统开关，
//    开着它的人里有相当一部分是前庭功能障碍者——视差、缩放这类大面积
//    位移是明确的眩晕诱因。这不是加分项，是无障碍的底线：
//    开了开关就**完全关掉视差**，退化成普通滚动，而不是"减半"。
//
// ③ **滚动位置只订阅一次。** 用 Animated.event + useNativeDriver 直接把
//    scrollY 喂给 Animated.Value，不要 setState——每帧 setState 会让整棵
//    树重渲染，比不做视差还卡。
import {
  AccessibilityInfo, Animated, Dimensions, Image, Platform,
  RefreshControl, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ContentItem, PlatformClient } from '@platform/core';

const { width: SCREEN_W } = Dimensions.get('window');
const HEADER_H = 220;          // 顶部大图高度
const CARD_MEDIA_H = 200;      // 卡片配图高度
const PARALLAX = 0.5;          // 背景位移 = 滚动距离 × 这个系数

/** 系统「减弱动态效果」开关。取不到时按**关闭**处理（即照常做视差）——
 *  与流量提醒那条相反：那里的代价是用户的钱，这里的代价只是少一点效果，
 *  而多数设备拿得到这个值。 */
function useReduceMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled?.()
      .then((v) => { if (alive) setReduce(!!v); })
      .catch(() => { /* 取不到就按 false */ });
    const sub = AccessibilityInfo.addEventListener?.('reduceMotionChanged', setReduce);
    return () => { alive = false; sub?.remove?.(); };
  }, []);
  return reduce;
}

function firstImage(c: ContentItem): string | null {
  return (c.media_urls ?? []).find((u) => /\.(jpe?g|png|webp)$/i.test(u)) ?? null;
}

export function DiscoverScreen({ client, baseUrl, onOpenAuthor }: {
  client: PlatformClient;
  baseUrl: string;
  onOpenAuthor?: (userId: number) => void;
}) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const reduceMotion = useReduceMotion();
  // ③ 只建一次，且只被 Animated.event 写
  const scrollY = useRef(new Animated.Value(0)).current;

  const load = async () => {
    setRefreshing(true);
    try { setItems(await client.contentFeed('latest')); } catch { /* 列表留空 */ }
    finally { setRefreshing(false); }
  };
  useEffect(() => { void load(); }, []);

  const onScroll = useMemo(
    () => Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }],
      { useNativeDriver: true }),   // ① 关键：不加这个就是 JS 线程逐帧算
    [scrollY],
  );

  // 顶部大图：向下拉时放大并下移（iOS 的经典弹性头），向上滚时以 0.5 倍速上移
  const headerTransform = reduceMotion ? [] : [
    {
      translateY: scrollY.interpolate({
        inputRange: [-HEADER_H, 0, HEADER_H],
        outputRange: [-HEADER_H / 2, 0, HEADER_H * PARALLAX],
        extrapolate: 'clamp' as const,
      }),
    },
    {
      scale: scrollY.interpolate({
        inputRange: [-HEADER_H, 0],
        outputRange: [2, 1],
        extrapolateRight: 'clamp' as const,
      }),
    },
  ];
  const titleOpacity = reduceMotion ? 1 : scrollY.interpolate({
    inputRange: [0, HEADER_H * 0.7],
    outputRange: [1, 0],
    extrapolate: 'clamp' as const,
  });

  return (
    <View style={styles.root}>
      <Animated.View style={[styles.header, { transform: headerTransform }]}>
        <View style={styles.headerBg} />
        <Animated.View style={{ opacity: titleOpacity }}>
          <Text style={styles.headerTitle}>发现</Text>
          <Text style={styles.headerSub}>
            {reduceMotion ? '已按系统设置关闭动效' : '看看大家在做什么'}
          </Text>
        </Animated.View>
      </Animated.View>

      <Animated.ScrollView
        style={styles.scroll}
        contentContainerStyle={{ paddingTop: HEADER_H, paddingBottom: 24 }}
        // 16ms ≈ 60fps。native driver 下这个值只影响 JS 侧回调频率，
        // 动画本身在 UI 线程跑，不受它限制
        scrollEventThrottle={16}
        onScroll={onScroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
      >
        {items.length === 0 && <Text style={styles.empty}>还没有内容，下拉刷新试试。</Text>}
        {items.map((c, i) => (
          <ParallaxCard
            key={c.id}
            item={c}
            index={i}
            baseUrl={baseUrl}
            scrollY={scrollY}
            reduceMotion={reduceMotion}
            onPressAuthor={() => onOpenAuthor?.(c.author_id)}
          />
        ))}
      </Animated.ScrollView>
    </View>
  );
}

/** 单张卡片：配图在卡片内部反向位移，卡片滚过屏幕时图像像在"窗后平移"。 */
function ParallaxCard({ item, index, baseUrl, scrollY, reduceMotion, onPressAuthor }: {
  item: ContentItem;
  index: number;
  baseUrl: string;
  scrollY: Animated.Value;
  reduceMotion: boolean;
  onPressAuthor: () => void;
}) {
  const img = firstImage(item);
  // 卡片大致的滚动区间。精确值要靠 onLayout 测，但那会引入每张卡一次
  // setState；这里用估算高度换取"零重渲染"——视差是观感，差几十像素无所谓。
  const CARD_H = img ? CARD_MEDIA_H + 120 : 120;
  const start = index * CARD_H - 400;
  const end = start + CARD_H + 800;

  const mediaTranslate = reduceMotion ? 0 : scrollY.interpolate({
    inputRange: [start, end],
    outputRange: [-CARD_MEDIA_H * 0.25, CARD_MEDIA_H * 0.25],
    extrapolate: 'clamp',
  });

  return (
    <View style={styles.card}>
      {img && (
        // overflow:hidden 的窗口 + 比窗口高的图 = 图在窗后平移而不露边
        <View style={styles.mediaWindow}>
          <Animated.View style={{ transform: [{ translateY: mediaTranslate }] }}>
            <Image
              source={{ uri: img.startsWith('http') ? img : baseUrl + img }}
              style={styles.media}
              resizeMode="cover"
            />
          </Animated.View>
        </View>
      )}
      <View style={styles.cardBody}>
        {!!item.title && <Text style={styles.cardTitle}>{item.title}</Text>}
        <Text numberOfLines={3} style={styles.cardText}>{item.body}</Text>
        <View style={styles.cardMeta}>
          <TouchableOpacity onPress={onPressAuthor}>
            <Text style={styles.author}>@{item.author_nickname}</Text>
          </TouchableOpacity>
          <Text style={styles.metaMuted}>
            ♥ {item.like_count} · 💬 {item.comment_count}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f5f6f8' },
  scroll: { flex: 1 },
  header: {
    position: 'absolute', top: 0, left: 0, right: 0, height: HEADER_H,
    justifyContent: 'flex-end', paddingBottom: 28, paddingHorizontal: 20,
  },
  headerBg: { ...StyleSheet.absoluteFillObject, backgroundColor: '#2f6fed' },
  headerTitle: { color: '#fff', fontSize: 30, fontWeight: '800' },
  headerSub: { color: '#dbeafe', marginTop: 4 },
  empty: { textAlign: 'center', color: '#6b7280', marginTop: 40 },
  card: {
    backgroundColor: '#fff', borderRadius: 14, marginHorizontal: 12, marginBottom: 14,
    overflow: 'hidden',
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 2 },
    }),
  },
  // 窗口比图矮：图上下各留出位移余量，平移时不会露出空白
  mediaWindow: { height: CARD_MEDIA_H, overflow: 'hidden' },
  media: { width: SCREEN_W - 24, height: CARD_MEDIA_H * 1.5, marginTop: -CARD_MEDIA_H * 0.25 },
  cardBody: { padding: 14, gap: 6 },
  cardTitle: { fontSize: 17, fontWeight: '700' },
  cardText: { color: '#374151', lineHeight: 20 },
  cardMeta: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  author: { color: '#2f6fed', fontWeight: '600' },
  metaMuted: { color: '#6b7280', fontSize: 12 },
});
