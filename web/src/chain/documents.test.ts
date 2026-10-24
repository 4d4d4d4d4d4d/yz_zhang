import { webcrypto } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { encryptDocument, decryptDocument, commitmentFor } from './documents';
afterEach(() => vi.unstubAllGlobals());
it('encrypts locally with randomized commitments, restores exact bytes and rejects tampering', async () => {
  vi.stubGlobal('crypto', webcrypto);
  const raw = new TextEncoder().encode('股东协议：份额 60% / 40%；财务凭证原文。');
  const first = await encryptDocument(raw, 'agreement.txt', 'text/plain');
  const second = await encryptDocument(raw, 'agreement.txt', 'text/plain');
  expect(first.archive.commitment).not.toBe(second.archive.commitment);
  expect(first.archive.ciphertext).not.toBe(second.archive.ciphertext);
  expect(JSON.stringify(first.archive)).not.toContain('股东协议');
  const restored = await decryptDocument(first.archive, first.recovery, first.archive.commitment);
  expect(Array.from(restored)).toEqual(Array.from(raw));
  await expect(decryptDocument(first.archive, second.recovery, first.archive.commitment)).rejects.toThrow();
  await expect(decryptDocument(first.archive, first.recovery, second.archive.commitment)).rejects.toThrow();
  const damaged = { ...first.archive, ciphertext: (first.archive.ciphertext.startsWith('00') ? '01' : '00') + first.archive.ciphertext.slice(2) };
  await expect(decryptDocument(damaged, first.recovery, first.archive.commitment)).rejects.toThrow();
  await expect(decryptDocument(first.archive, { ...first.recovery, salt: second.recovery.salt }, first.archive.commitment)).rejects.toThrow();
  expect(await commitmentFor(raw, first.recovery.salt)).toBe(first.archive.commitment);
});
it('rejects empty and oversized documents', async () => {
  vi.stubGlobal('crypto', webcrypto);
  await expect(encryptDocument(new Uint8Array(), 'empty', '')).rejects.toThrow();
  await expect(encryptDocument(new Uint8Array(10 * 1024 * 1024 + 1), 'large', '')).rejects.toThrow();
});
