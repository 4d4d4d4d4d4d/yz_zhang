// PRLX-051/053 运动层的行为（79 号 spec）。
//
// 源码扫描能看出「CSS 里有 reduced-motion 分支」；它看不出**组件在开关
// 打开时到底还动不动**——而那正是这条约束的要害：
// 减半的位移对前庭功能障碍者仍然是位移。
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ParallaxHero, Reveal, TechBackdrop } from './Motion';

/** 把 `prefers-reduced-motion` 打开或关上。
 *
 * jsdom 没有 matchMedia，所以这里装一个：只认这一条 query，
 * 其余返回不匹配——比返回「全部匹配」安全，那会让别的媒体查询误触发。 */
function setReducedMotion(on: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: on && q.includes('prefers-reduced-motion'),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('PRLX-051 reduced-motion 是完全关闭，不是减半', () => {
  it('开着开关时：背景层不挂滚动量，位移为 0', async () => {
    setReducedMotion(true);
    render(<TechBackdrop />);
    const el = await screen.findByTestId('tech-backdrop');
    expect(el.dataset.reduced).toBe('true');

    fireEvent.scroll(window, { target: { scrollY: 400 } });
    // 位移由 --sy 换算；不写这个变量就等于 transform: none
    await waitFor(() => expect(el.style.getPropertyValue('--sy')).toBe(''));
  });

  it('关着开关时：滚动量写进 CSS 变量（而不是 setState）', async () => {
    setReducedMotion(false);
    render(<TechBackdrop />);
    const el = await screen.findByTestId('tech-backdrop');
    expect(el.dataset.reduced).toBe('false');
    // 挂载时就写一次，不必等第一次滚动
    await waitFor(() => expect(el.style.getPropertyValue('--sy')).not.toBe(''));
  });

  it('Reveal 在 reduced-motion 下直接到终态', async () => {
    setReducedMotion(true);
    render(<Reveal><p>内容</p></Reveal>);
    const el = await screen.findByText('内容');
    // `in` 类表示已到终态（CSS 里 .reveal.in 是 transform: none）
    await waitFor(() => expect(el.parentElement?.className).toContain('in'));
  });

  it('没有 IntersectionObserver 时也要看得到内容（不能把内容藏了）', async () => {
    setReducedMotion(false);
    const saved = globalThis.IntersectionObserver;
    // @ts-expect-error 故意删掉，模拟老浏览器
    delete globalThis.IntersectionObserver;
    render(<Reveal><p>兜底内容</p></Reveal>);
    const el = await screen.findByText('兜底内容');
    await waitFor(() => expect(el.parentElement?.className).toContain('in'));
    globalThis.IntersectionObserver = saved;
  });
});

describe('PRLX-050 装饰层不挡功能', () => {
  it('背景是装饰：不进无障碍树、不吃指针事件', async () => {
    setReducedMotion(false);
    render(<TechBackdrop />);
    const el = await screen.findByTestId('tech-backdrop');
    expect(el.getAttribute('aria-hidden')).toBe('true');
    // pointer-events 由 .tech-backdrop 的样式给（jsdom 不算样式），
    // 这里钉住 class 名，样式表那条由 test_motion_layer.py 扫
    expect(el.className).toContain('tech-backdrop');
  });

  it('hero 的内容层不随滚动移动——标题与按钮漂移会让人点不准', async () => {
    setReducedMotion(false);
    render(<ParallaxHero title="任务广场" subtitle="副标题"><button>发布</button></ParallaxHero>);
    const hero = await screen.findByTestId('parallax-hero');
    const content = hero.querySelector('.hero-content') as HTMLElement;
    fireEvent.scroll(window, { target: { scrollY: 600 } });
    // 只有 .hero-layer 会被 --sy 驱动；内容层没有任何 inline transform
    await waitFor(() => expect(content.style.transform).toBe(''));
    expect(screen.getByText('发布')).toBeTruthy();
  });
});
