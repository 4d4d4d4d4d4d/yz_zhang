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
