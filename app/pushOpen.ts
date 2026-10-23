// NTF-073（268 号 spec）用户点了推送进来：公告的推送带着 announcement_id，报给服务端「从推送点开」。
// 接 expo-notifications 后在 addNotificationResponseReceivedListener 里调用它（真机推送通道是「外」，见 App.tsx 的 getPushToken）。
import type { PlatformClient } from '@platform/core';

/** 推送附带的数据里有正整数的 announcement_id 才报；其他推送（任务、资金）照旧只打开 App。报失败不影响打开。 */
export async function reportPushOpened(client: PlatformClient, data: unknown): Promise<boolean> {
  const id = (data as { announcement_id?: unknown } | null)?.announcement_id;
  if (typeof id !== 'number' || !Number.isInteger(id) || id <= 0) return false;
  try {
    await client.pushOpened(id);
    return true;
  } catch {
    return false;
  }
}
