// Client-side encryption. Neither plaintext nor recovery material is sent to the RPC/server.
export type Archive = { schema: 'opc-record-archive-v1'; algorithm: 'AES-256-GCM'; iv: string; ciphertext: string; commitment: string };
export type Recovery = { schema: 'opc-record-recovery-v1'; key: string; salt: string; name: string; type: string };
const encode = new TextEncoder();
const hex = (bytes: Uint8Array) => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
const fromHex = (value: string) => {
  if (!/^(?:[0-9a-f]{2})+$/i.test(value)) throw new Error('加密文件格式错误');
  return Uint8Array.from(value.match(/.{2}/g)!, h => parseInt(h, 16));
};
export async function commitmentFor(data: Uint8Array<ArrayBuffer>, salt: string) {
  if (!/^[0-9a-f]{64}$/i.test(salt)) throw new Error('恢复盐格式错误');
  const digest = hex(new Uint8Array(await crypto.subtle.digest('SHA-256', data)));
  return '0x' + hex(new Uint8Array(await crypto.subtle.digest('SHA-256', encode.encode(`opc-business-record-v1\n${salt.toLowerCase()}\n${digest}`))));
}
export async function encryptDocument(data: Uint8Array<ArrayBuffer>, name: string, type: string): Promise<{ archive: Archive; recovery: Recovery }> {
  if (data.length === 0 || data.length > 10 * 1024 * 1024) throw new Error('文件须为 1 字节至 10 MB');
  const rawKey = crypto.getRandomValues(new Uint8Array(32)), iv = crypto.getRandomValues(new Uint8Array(12));
  const salt = hex(crypto.getRandomValues(new Uint8Array(32)));
  const commitment = await commitmentFor(data, salt);
  const key = await crypto.subtle.importKey('raw', rawKey, 'AES-GCM', false, ['encrypt']);
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: encode.encode(commitment) }, key, data);
  return {
    archive: { schema: 'opc-record-archive-v1', algorithm: 'AES-256-GCM', iv: hex(iv), ciphertext: hex(new Uint8Array(ciphertext)), commitment },
    recovery: { schema: 'opc-record-recovery-v1', key: hex(rawKey), salt, name, type },
  };
}
export async function decryptDocument(archive: Archive, recovery: Recovery, expectedCommitment: string) {
  if (archive.schema !== 'opc-record-archive-v1' || recovery.schema !== 'opc-record-recovery-v1' || archive.algorithm !== 'AES-256-GCM'
      || !/^[a-f0-9]{64}$/i.test(recovery.key) || !/^[a-f0-9]{24}$/i.test(archive.iv) || archive.commitment !== expectedCommitment) throw new Error('档案与链上摘要不匹配');
  const key = await crypto.subtle.importKey('raw', fromHex(recovery.key), 'AES-GCM', false, ['decrypt']);
  const result = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: fromHex(archive.iv), additionalData: encode.encode(archive.commitment) }, key, fromHex(archive.ciphertext)));
  if (await commitmentFor(result, recovery.salt) !== expectedCommitment) throw new Error('原文完整性校验失败');
  return result;
}
export function downloadFile(contents: BlobPart, name: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
