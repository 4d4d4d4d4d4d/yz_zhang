// APPB-003 让 Metro 看得见仓库里的 @platform/core。
//
// `@platform/core` 不是一个装好的包，是 `file:../packages/core` 链过来的
// **TypeScript 源码，而且在 app/ 之外**。Metro 默认只监视项目根以下的文件，
// 于是两件事都会断：
//
// ① 解析不到源码本身 → 要把 packages/core 加进 watchFolders；
// ② core 自己的依赖找不着 → 要让 nodeModulesPaths 同时看 app/node_modules
//    与仓库根 node_modules（npm 会把公共依赖提到根上）。
//
// 用 expo export 同时验证 iOS/Android 的 Metro 解析；设备行为另做真机验证。
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, '..');

const config = getDefaultConfig(projectRoot);

config.watchFolders = [path.resolve(workspaceRoot, 'packages/core')];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
];
// npm 会把版本冲突的依赖安装到 react-native/node_modules 等嵌套目录。
// 禁止层级查找会让 virtualized-lists 在真实打包时消失（类型检查发现不了）。
config.resolver.disableHierarchicalLookup = false;
// React 必须始终来自 App，避免共享源码意外解析到 Web 的 React。
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === 'react' || moduleName.startsWith('react/') || moduleName === 'react-native') {
    return context.resolveRequest({
      ...context,
      disableHierarchicalLookup: true,
      nodeModulesPaths: [path.resolve(projectRoot, 'node_modules')],
    }, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
