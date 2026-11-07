
# 129 端侧模型下载、断点续传、分块校验与启用；浏览器端模型评估

> 状态：本批实现（V160）。编号 SBX-111~119。
> 来源：128 号 spec「没做的」SBX-111 / SBX-112（BACKLOG V160）；用户 2026-10-14：「能够在端侧手机上跑量化小模型从而信息不上传云端」。
> 只增不减：沙箱、本机助手、模型目录（128 号）不变；App 的「端侧模型」一块从「只列目录」变成「可以下载、校验、启用、删除」。
> 新增 App 依赖 `expo-file-system ~17.0.1`（Expo 51 已经自带同版本，这里改为显式声明并写进锁文件）。

## 0. 要解决的问题

V158 有了目录和 `LocalModel` 注入点，但手机上没法把模型拿下来：没有下载、没有续传、没有校验，下架了也不知道该删。

## 1. 业界怎么做（带来源链接）

- 移动端大文件：Expo `FileSystem.createDownloadResumable` 支持暂停后用 `savable()` / resumeData 续传（<https://docs.expo.dev/versions/v51.0.0/sdk/filesystem/>）。
- 完整性：llama.rn 下载预编译库后做 SHA-256 校验（<https://github.com/mybigday/llama.rn>）；Hugging Face 对 LFS 文件公布 sha256。这里同样：只认目录登记的 sha256，对不上就删。
- 浏览器端：WebLLM 只走 WebGPU，1B 级 4 bit 模型约 695 MB 下载、运行约 880 MB 显存（<https://pinggy.io/blog/run_llm_in_browser_webgpu/>，二手整理）；
  iOS 26 的 Safari 才有 WebGPU（<https://appdevelopermagazine.com/webgpu-in-ios-26/>，二手）。浏览器存储随时可能被清理、每个浏览器各存一份——**所以浏览器端暂不提供模型**，界面如实说明（SBX-112，有意不做，理由见第 7 节）。

## 2. 数据

全部在手机上：`AsyncStorage` 的 `sandbox.models`（已安装：标识、名称、sha256、大小、路径、校验时间）与 `sandbox.dl.<标识>`（续传信息）；模型文件在应用文档目录 `models/` 下。服务端不新增任何东西。

## 3. 接口（App 模块 `modelStore.ts` 与 SDK）

| 编号 | 内容 |
|---|---|
| SBX-111 | `downloadModel`：先看剩余空间（要 1.1 倍大小），从登记地址直接下载；暂停（`pauseDownload`）后存下续传信息，再点续上；下完按 4 MB 一块读出、`base64ToBytes` 解码、增量 `Sha256` 校验；对不上**删文件、不登记**并说清楚 |
| SBX-113 | `staleModels`：手机上装着、但平台已下架或换了 sha256 的，提示删除（大小写不敏感比对） |
| SBX-114 | `removeModel`：删文件、清续传信息、从已安装里去掉，并停用当前模型 |
| SBX-115 | `activateModel` / `registerRuntime`：原生构建注入推理运行时后加载并设为本机助手的模型；没有运行时如实说「已下载并校验，但这个安装包里没有端侧推理运行时」，继续用本机规则；加载失败（内存不够）同样如实说 |
| SBX-116 | SDK `base64ToBytes`：不依赖 atob / Buffer，Hermes 上可用 |
| SBX-112 | Web 沙箱页显示这个浏览器有没有 WebGPU，以及为什么浏览器端暂不提供模型 |

## 4. 两端

- **App**「隐私沙箱 → 端侧模型」：每个模型「下载并校验」→ 进度（下载 / 校验百分比）与「暂停」→「已下载，校验通过」+「启用」「删除」；已下架的单独一行「建议删掉」。
- **Web**：只多一行说明（见 SBX-112）。

## 5. 隐私、授权与边界

- 模型文件不经平台服务器；下载地址与 sha256 来自四眼上架的目录（128 号）。
- 校验不过的文件立刻删除，不会被加载。
- 不悄悄回退云端：没有运行时、内存不够、校验失败，都在界面上说清楚，用本机规则。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| 校验不过就删 | 去掉删除 → `modelStore.test.tsx`「sha256 对不上」红 |
| 真的比对 sha256 | 校验恒为真 → 同上红 |
| 分块（12 MB 跨过 4 MB 边界） | 校验进度至少 3 次 |
| 续传 | 暂停后再下必须走 `resumeAsync` 并带上续传信息 |
| 下架提示大小写不敏感 | 测试里目录 sha256 是大写——这条测试先红过一次，修了 `staleModels` 的真问题 |
| 空间不够在下载前就说 | 不发起下载 |
| base64 解码 | `sandbox.test.ts`：各种长度与补位 |

## 7. 没做的

- **SBX-110 原生推理运行时**（llama.rn / ExecuTorch 适配、真机测速发热）：仍是「外」，要 Expo 开发构建与真机；`registerRuntime` 注入点已就绪。
- **SBX-112 浏览器端模型**：有意不做（现阶段）。理由：模型几百 MB、每个浏览器各存一份且可能被清理；iOS 上要 Safari 26 才有 WebGPU；用户要的是「手机上」。
  桌面端有明确需求时再评估 WebLLM。
- **SBX-119 后台下载**（App 切到后台时继续下）：要原生后台任务配置，随 SBX-110 的原生构建一起做。
