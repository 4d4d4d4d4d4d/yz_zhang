import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import { LaunchReadiness } from './Admin';
const { adminVendors } = vi.hoisted(() => ({ adminVendors: vi.fn() }));
vi.mock('../store', () => ({ useApp: () => ({ client: { adminVendors } }) }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it('shows missing integration truthfully without converting checks into commercial approval', async () => {
  adminVendors.mockResolvedValue({ commercial_readiness: { environment: 'test', checks_passed: 7, checks_total: 17,
    checks: [{ code: 'provider_payment', passed: false, category: 'integration' }],
    vendors: [{ kind: 'payment', configured_grade: 'mock', registered_non_mock_implementations: [] }] } });
  render(<LaunchReadiness />);
  expect(adminVendors).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '检查当前环境' }));
  await waitFor(() => expect(screen.getByText(/配置检查 7\/17/)).toBeTruthy());
  expect(screen.getByText(/还没有正式适配实现，并非仅缺密钥/)).toBeTruthy();
  expect(screen.getByText(/不代表已获准开展真实交易/)).toBeTruthy();
});
it('reports failure instead of presenting an empty successful checklist', async () => {
  adminVendors.mockRejectedValue(new Error('暂时无法读取'));
  render(<LaunchReadiness />);
  fireEvent.click(screen.getByRole('button', { name: '检查当前环境' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('网络错误'));
  expect(screen.queryByText(/配置检查.*通过/)).toBeNull();
});
