# 45 App 发现流的视差滚动（PRLX / APP-002）

> 补 13 号 spec 的 APP-002「发现：短视频流 / 关注 / 圈层 tab」——
> App 此前只有 任务 / 发布 / 钱包 / 通知 / 我的 五个 tab，没有内容消费入口。

## 0. 视差不是「加个动画」

在 React Native 上做视差有三条**非做不可**的约束，每一条不这样做都会
实打实地伤到人或伤到体验。它们不是优化项，是这个效果成立的前提。

### PRLX-010 必须走 native driver

RN 的 `Animated` 默认在 **JS 线程**逐帧计算。而滚动时 JS 线程本来就忙
（列表渲染、事件回调都在上面），视差会肉眼可见地掉帧、跟手感发飘——
**做出来比不做还差**。

`useNativeDriver: true` 把动画搬到 UI 线程。代价是**只能动 `transform`
与 `opacity`**：动 `height` / `top` / `backgroundColor` 会在运行时抛
`Style property 'x' is not supported by native animated module`，
而那是**真机上才炸，CI 看不见**。所以这条有测试钉着。

### PRLX-020 必须尊重「减弱动态效果」

iOS 与 Android 都有这个系统开关。开着它的人里有相当一部分是**前庭功能
障碍者**——视差、缩放这类大面积位移是明确的眩晕诱因。

**这是无障碍底线，不是加分项。** 而且要完全关掉，不是「减半」：
减半的位移仍然会让人晕，只是让开发者觉得自己做了点什么。

还要处理「使用中被打开」：订阅 `reduceMotionChanged`，而不是只在挂载时读一次。

并且**要让用户看得见**——悄悄关掉动效，用户会以为是 App 坏了，
所以副标题会显示「已按系统设置关闭动效」。

### PRLX-030 滚动位置不能进 setState

`Animated.event` + native driver 直接把 `scrollY` 喂给 `Animated.Value`。
每帧 `setState` 会让整棵树重渲染，**比不做视差还卡**。

## 1. 其它设计判断

**卡片滚动区间用估算而不是 `onLayout` 实测。** 精确值要靠 `onLayout`，
但那会给每张卡引入一次 `setState`。视差是观感，差几十像素没人看得出来——
用估算换「零重渲染」是对的取舍。

**配图窗口 `overflow: hidden` + 图比窗口高 25%。** 图在窗后平移而不露边。
这是视差卡片的标准做法，也是为什么 `media` 的高度是 `1.5×` 窗口高、
`marginTop` 是 `-25%`。

**取不到 reduce-motion 时按「关闭」处理**（即照常做视差）。
这与 CNT-014 流量提醒那条**相反**：那里取不到网络类型就按「可能是流量」
处理，因为代价是用户的钱；这里的代价只是少一点效果，而多数设备拿得到这个值。
判断依据是**代价落在谁身上**，不是「保守一点总没错」。

## 2. 条目

- **PRLX-001** `app/Discover.tsx`：顶部大图弹性头（下拉放大、上滚 0.5 倍速
  上移、标题渐隐）+ 卡片内配图反向位移。
- **PRLX-010/011** 全部动画走 native driver，且只动 `transform` / `opacity`。
- **PRLX-012** 滚动位置只经 `Animated.event`，不进 `setState`。
- **PRLX-020/021/022** 尊重 `AccessibilityInfo.isReduceMotionEnabled`，
  订阅 `reduceMotionChanged`，开启时**完全**关闭视差，并在界面上如实说明。
- **PRLX-030** 接入 App 的「发现」tab（APP-002）。

### 顺带补上的一道闸门

- **PRLX-002** CI 新增 `app/*.tsx` 的 **esbuild 解析检查**。

  `app/` 不在 npm workspaces、没有 tsconfig，CI 从来不碰它——
  这正是 V63 那个「App 侧被诉方开不了口」的缺口能一直躺着的原因（DSPR-042）。
  完整类型检查要装 expo/react-native，会改变整仓的安装行为，我仍然没做；
  但**解析不需要那些依赖**：esbuild 能抓语法与 JSX 错误，成本接近零。

  这不是类型检查，是把「改完连解析都不过」挡在真机之前。
  已实测：把 `Discover.tsx` 改坏一个括号，这条闸门变红。

## 3. 已知缺口

- **PRLX-040 没有真机验证。** 本环境没有模拟器，所有断言都是对源码的。
  视差的手感、native driver 是否真的没掉帧、reduce-motion 在真机上的行为，
  都必须在真机上再看一遍。**源码断言能保证「写法是对的」，保证不了「看起来是对的」。**
- **PRLX-041 `app/` 仍未类型检查**（DSPR-042 未关闭）。本批把它从
  「什么都不检查」推进到「至少解析得过」。
- **PRLX-042 视频没进发现流。** `VideoFeed` 目前只在 Web 上；
  App 侧的沉浸流要用 `expo-av`，属于加依赖，与 NTF-021 同一类问题。
- **PRLX-043 没有做列表虚拟化。** 现在是 `ScrollView` 全量渲染，
  内容超过百条会吃内存。换 `Animated.FlatList` 即可，但那要重新处理
  卡片区间估算——本批内容量还远没到。
