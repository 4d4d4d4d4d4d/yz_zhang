/**
 * TASK-022d（390 号 spec）把服务端给的文件地址变成 App 能直接加载的地址。
 *
 * 服务端返回的上传文件地址是相对路径（`/api/v1/files/…`）。网页和服务端同源，`<img src>` 直接用；
 * App 不同源，React Native 的 `<Image>` 加载相对路径会静默失败——V417 发现任务详情页的交付预览就是这样在真机上一张都出不来。
 * 两端拼法收成一处：完整的 http(s) 地址原样返回；以 `/` 开头的拼上服务端地址；别的（空、畸形、`javascript:` 之类）一律给空串，不画。
 */
export function mediaUri(baseUrl: string, path: unknown): string {
  if (typeof path !== 'string') return '';
  if (/^https?:\/\//i.test(path)) return path;
  if (!path.startsWith('/') || path.startsWith('//')) return '';
  return `${String(baseUrl || '').replace(/\/+$/, '')}${path}`;
}
