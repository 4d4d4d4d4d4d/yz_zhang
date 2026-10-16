// APP-092 Web 页面错误边界（183 号 spec）：一页渲染出错只坏这一页，导航还在；换一页自动复位。
import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RouteBoundary from './RouteBoundary';

function Boom(): JSX.Element { throw new TypeError('rows.map is not a function'); }

describe('APP-092 Web 页面错误边界', () => {
  beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}); });
  afterEach(() => vi.restoreAllMocks());

  it('一页出错：导航在、换成说明卡；只记错误类型；点到别的页正常显示', () => {
    render(<MemoryRouter initialEntries={['/bad']}>
      <nav><Link to="/ok">去好的那页</Link></nav>
      <RouteBoundary><Routes><Route path="/bad" element={<Boom />} /><Route path="/ok" element={<p>好的那页</p>} /></Routes></RouteBoundary>
    </MemoryRouter>);
    expect(screen.getByRole('alert', { name: '这一页没加载出来' })).toBeTruthy();
    expect(screen.getByText('去客服')).toBeTruthy();
    expect(console.error).toHaveBeenCalledWith('page_render_failed', 'TypeError');
    fireEvent.click(screen.getByText('去好的那页'));
    expect(screen.getByText('好的那页')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
