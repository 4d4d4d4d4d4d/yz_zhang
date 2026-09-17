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
// 注意：这个文件是本批**唯一没有被机器验证过**的改动。验证它要真的起 Metro，
// 而 Metro 要连设备或模拟器，本环境做不到。写法照 Expo 的 monorepo 文档，
// 但「对不对」目前只有判断背书——记在 APPB-051，不当作已验证。
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
// 同一个包在两处各解析一份会让 React 出现两个实例（hooks 直接报错），
// 所以关掉向上逐层查找，只认上面这两个目录。
config.resolver.disableHierarchicalLookup = true;

module.exports = config;
