// PRLX-057 App 侧运动层的**唯一一份实现**（79 号 spec）。
//
// 45 号 spec 为发现流立了三条约束，它们不是优化项、是效果成立的前提：
//
// ① `useNativeDriver: true`——不加就是 JS 线程逐帧算，滚动时肉眼掉帧，
//    **做出来比不做还差**；代价是只能动 transform 与 opacity，
//    动别的属性会在**真机上**抛错而 CI 看不见。
// ② 系统「减弱动态效果」开着时**完全关掉**，不是减半——开着它的人里
//    有相当一部分是前庭功能障碍者，减半仍然会让人难受。
// ③ 滚动回调里不 setState，否则每帧重渲染整棵树。
//
// 这三条抄第二遍必然漏掉一条（**第二份实现必然抄漏**，UI-075/TEAM-021
// 反复引用的那句），所以 `Discover` 与任务详情 hero 共用这里的实现。
import { useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, Animated } from 'react-native';

/** 系统「减弱动态效果」开关。取不到时按**关闭**处理（即照常做效果）：
 *  代价只是少一点观感，而多数设备拿得到这个值。 */
export function useReduceMotion(): boolean {
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

/** 一个只被 `Animated.event` 写的滚动量，以及配套的 onScroll。
 *
 * `scrollY` 用 ref 保证只建一次：每次渲染新建一个 `Animated.Value`
 * 会让动画从头开始跳一下。 */
export function useScrollDriver() {
  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = useMemo(
    () => Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }],
      { useNativeDriver: true }),
    [scrollY],
  );
  return { scrollY, onScroll };
}

/** 顶部大图的视差 transform：下拉放大下移，上滚以 `factor` 倍速上移。
 *
 * `reduce` 为真时返回空数组——**不动**，而不是动得少一点。 */
export function heroTransform(
  scrollY: Animated.Value, headerHeight: number, reduce: boolean, factor = 0.5,
) {
  if (reduce) return [];
  return [
    {
      translateY: scrollY.interpolate({
        inputRange: [-headerHeight, 0, headerHeight],
        outputRange: [-headerHeight / 2, 0, headerHeight * factor],
        extrapolate: 'clamp' as const,
      }),
    },
    {
      scale: scrollY.interpolate({
        inputRange: [-headerHeight, 0],
        outputRange: [2, 1],
        extrapolateRight: 'clamp' as const,
      }),
    },
  ];
}

/** 标题随滚动淡出。`reduce` 为真时恒为 1。 */
export function heroTitleOpacity(
  scrollY: Animated.Value, headerHeight: number, reduce: boolean,
): Animated.AnimatedInterpolation<number> | number {
  if (reduce) return 1;
  return scrollY.interpolate({
    inputRange: [0, headerHeight * 0.7],
    outputRange: [1, 0],
    extrapolate: 'clamp' as const,
  });
}

/** 列表里一张卡片的配图视差：图在 `overflow:hidden` 的窗口后平移。
 *
 * 卡片的滚动区间用**估算高度**算，不用 `onLayout` 测：测量会给每张卡
 * 引入一次 setState，那正是 PRLX-030 要避免的。视差是观感，
 * 差几十像素无所谓；每帧重渲染整棵树才是问题。
 */
export function cardMediaTranslate(
  scrollY: Animated.Value, index: number, cardHeight: number,
  mediaHeight: number, reduce: boolean,
): Animated.AnimatedInterpolation<number> | number {
  if (reduce) return 0;
  const start = index * cardHeight - 400;
  return scrollY.interpolate({
    inputRange: [start, start + cardHeight + 800],
    outputRange: [-mediaHeight * 0.25, mediaHeight * 0.25],
    extrapolate: 'clamp' as const,
  });
}
