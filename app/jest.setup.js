// APP-070 测试环境里的原生模块替身。
//
// 这几个包在真机上是原生模块，jest 里没有；官方给了 mock。
// **这也是这批测试的边界**：替身能证明界面逻辑对，不能证明真机上跑得起来。
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'));

jest.mock('expo-network', () => ({
  getNetworkStateAsync: async () => ({ isConnected: true, isInternetReachable: true }),
}));

jest.mock('expo-location', () => ({
  requestForegroundPermissionsAsync: async () => ({ status: 'granted' }),
  getCurrentPositionAsync: async () => ({ coords: { latitude: 31.2, longitude: 121.5 } }),
}));

// APP-072 相册/相机。真机上是原生模块，jest 里给替身。
// 默认返回一张极小的合法 base64 图：测试要验的是「选图→上传→拿到 ref→提交」
// 这条链，不是图片本身。单条用例可以用 jest.spyOn 改掉返回值来走失败分支。
// `__esModule: true` 不是摆设：没有它，babel 的 `import * as X` 互操作会
// **拷一份**导出对象给组件，于是测试里 `jest.spyOn` 改的是另一个对象，
// 组件拿到的还是默认替身——两条走失败分支的用例因此静默地测不到东西。
jest.mock('expo-image-picker', () => ({
  __esModule: true,
  requestCameraPermissionsAsync: async () => ({ status: 'granted' }),
  requestMediaLibraryPermissionsAsync: async () => ({ status: 'granted' }),
  launchCameraAsync: async () => ({
    canceled: false,
    assets: [{ base64: 'AAAA', mimeType: 'image/jpeg', uri: 'file:///c.jpg' }],
  }),
  launchImageLibraryAsync: async () => ({
    canceled: false,
    assets: [{ base64: 'AAAA', mimeType: 'image/jpeg', uri: 'file:///l.jpg' }],
  }),
}));
