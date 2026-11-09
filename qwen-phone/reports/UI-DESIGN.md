# 界面改版 2026-10-15

当前实现：深石墨背景、青蓝高光、渐变材质球、悬浮输入框、短文案；低频设置合并进“语音与更多”，画像与任务保持折叠；确认查询/笔记的具体内容仍完整显示。正式用户资料库未初始化。

动态：球体浮动与轨道、消息入场、按钮反馈；遵循 prefers-reduced-motion，后台暂停球体装饰动画。动画使用 CSS，无新增远程字体、图片或统计脚本。

验证：实际网页锁定态、无数据静态预览主界面、390px 布局 scrollWidth=390；语音 mock 回归通过。原生 APK 只完成主题适配及构建，实际 WebView 仍待安装验收。

设计参考：
- https://linear.app/now/how-we-redesigned-the-linear-ui
- https://developer.apple.com/design/human-interface-guidelines/materials

Figma 插件已查找到但尚未连接；此次是代码实现，没有声称已经创建 Figma 设计稿。design/interface.css 为样式源的参考副本，部署实际使用 agent/index.html 内联样式，修改需同步。
