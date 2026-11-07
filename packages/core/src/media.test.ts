import { describe, expect, it } from 'vitest';
import { mediaUri } from './media';

describe('TASK-022d 文件地址（390 号 spec）', () => {
  it('相对路径拼上服务端地址，末尾斜杠不重复', () => {
    expect(mediaUri('https://api.x.com', '/api/v1/files/abc')).toBe('https://api.x.com/api/v1/files/abc');
    expect(mediaUri('https://api.x.com/', '/api/v1/files/abc')).toBe('https://api.x.com/api/v1/files/abc');
    expect(mediaUri('', '/api/v1/files/abc')).toBe('/api/v1/files/abc');
  });

  it('完整地址原样返回', () => {
    expect(mediaUri('https://api.x.com', 'https://cdn.x.com/a.png')).toBe('https://cdn.x.com/a.png');
  });

  it('空、畸形、协议相对、别的协议一律不画', () => {
    for (const p of ['', null, undefined, 3, 'files/abc', '//evil.com/a.png', 'javascript:alert(1)', 'data:image/png;base64,AAAA']) {
      expect(mediaUri('https://api.x.com', p)).toBe('');
    }
  });
});
