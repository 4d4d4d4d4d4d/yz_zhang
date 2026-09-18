// APPB-002 没有这个文件，`expo start` 起不来。
//
// Expo 的 Metro 靠 `babel-preset-expo` 转 JSX 与 TypeScript。preset 是通过
// babel.config.js 加载的，不存在这个文件就没有 preset，第一个 `<View>` 就
// 是语法错误。这不是可调优的配置，是缺了就跑不起来的必需品——
// 而 `app/` 此前一次都没被真正启动过，所以这个洞躺了很久没人踩到。
module.exports = function (api) {
  api.cache(true);
  return { presets: ['babel-preset-expo'] };
};
