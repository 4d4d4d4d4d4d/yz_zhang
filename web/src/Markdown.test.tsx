// CNT-003 Markdown 渲染的安全属性。
//
// 博客正文是别人写的、所有人都会看——这条路径上的 XSS 不是「可能有」，
// 是「一定会被人试」。这些断言钉的就是那几个试法。
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown } from './Markdown';

describe('Markdown', () => {
  it('HTML 标签被当作纯文本，不进 DOM', () => {
    const { container } = render(
      <Markdown text={'<img src=x onerror="alert(1)">\n<script>alert(2)</script>'} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    // 原文仍然看得见——是「显示成文字」，不是「悄悄吞掉」
    expect(container.textContent).toContain('onerror');
  });

  it('javascript: 链接不会变成可点的 href', () => {
    const { container } = render(<Markdown text={'[点我](javascript:alert(1))'} />);
    expect(container.querySelector('a')).toBeNull();
    expect(screen.getByText('点我')).toBeTruthy();   // 文字保留，作者看得出写错了
  });

  it('data: 图片也拒绝', () => {
    const { container } = render(
      <Markdown text={'![x](data:text/html;base64,PHNjcmlwdD4=)'} />,
    );
    expect(container.querySelector('img')).toBeNull();
  });

  it('正常的 http 链接与站内相对路径放行', () => {
    const { container } = render(
      <Markdown text={'[站外](https://example.com) [站内](/tasks/1)'} />,
    );
    const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['https://example.com', '/tasks/1']);
    // 站外链接必须带 noopener，否则新窗口能反向操纵原页面
    expect(container.querySelector('a')?.getAttribute('rel')).toContain('noopener');
  });

  it('标题/列表/代码块/引用都渲染成对应元素', () => {
    const { container } = render(
      <Markdown text={'# 标题\n- 一\n- 二\n> 引用\n```\ncode\n```'} />,
    );
    expect(container.querySelector('h2')?.textContent).toBe('标题');
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelector('blockquote')?.textContent).toBe('引用');
    expect(container.querySelector('pre code')?.textContent).toBe('code');
  });

  it('行内加粗与代码', () => {
    const { container } = render(<Markdown text={'这是**粗的**和`码`'} />);
    expect(container.querySelector('strong')?.textContent).toBe('粗的');
    expect(container.querySelector('code')?.textContent).toBe('码');
  });
});
