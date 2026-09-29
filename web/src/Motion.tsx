// PRLX-050~056 web 侧的视觉运动层（79 号 spec）。
//
// 45 号 spec 为 App 立过三条约束，这里逐条对应到 web：
//
// ① **只动 transform / opacity**。动 top / height / margin 会在滚动时触发重排，
//    做出来比不做还卡（RN 那边是真机上直接抛错）。
//
// ② **`prefers-reduced-motion` 是完全关闭，不是减半**。开着这个开关的人里
//    有相当一部分是前庭功能障碍者，大面积位移是明确的眩晕诱因——
//    减半仍然会让人难受。
//
// ③ **滚动回调里不 setState**。每帧 setState 会让整棵树重渲染。这里的做法是
//    一个 scroll 监听 + rAF 节流，把滚动量写进 **CSS 变量**，位移由 CSS
//    的 transform 完成——React 一次都不重渲染。
import { useEffect, useRef, useState, type ReactNode } from 'react';

/** 系统「减弱动态效果」开关。取不到时按**关闭**处理（即照常做效果）：
 *  代价只是少一点观感，而多数浏览器都拿得到这个值。 */
export function useReducedMotion(): boolean {
  // **同步**读一次，不是先 false 再在 effect 里纠正：
  // 默认 false 的话，开着开关的设备上仍然会有一帧挂上滚动监听并写入位移——
  // 测试当场抓到了这一帧（`--sy` 被写成了 '0'）。
  const [reduce, setReduce] = useState(() => {
    try {
      return !!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    } catch {
      return false;      // 取不到就按关闭处理：代价只是少一点观感
    }
  });
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    setReduce(mq.matches);
    const on = (e: MediaQueryListEvent) => setReduce(e.matches);
    mq.addEventListener?.('change', on);
    return () => mq.removeEventListener?.('change', on);
  }, []);
  return reduce;
}

/** 把窗口滚动量写进一个 CSS 变量（`--sy`，单位 px 的裸数字）。
 *
 * 一个监听、一帧一次写、**零重渲染**。位移全部在 CSS 里按系数换算，
 * 所以要改视差强度不用碰 JS。 */
function useScrollVar(ref: React.RefObject<HTMLElement>, enabled: boolean) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    let frame = 0;
    const write = () => {
      frame = 0;
      el.style.setProperty('--sy', String(window.scrollY));
    };
    const onScroll = () => {
      // rAF 节流：滚动事件一帧可能来好几次，写一次就够
      if (!frame) frame = window.requestAnimationFrame(write);
    };
    write();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [ref, enabled]);
}

/** 全站固定背景：网格 + 两处辉光，随滚动**慢速**位移。
 *
 * 挂在 App 根上，只有一个实例。`aria-hidden` 且不吃指针事件——
 * 它是装饰，不该出现在无障碍树里，也不该挡住任何按钮。 */
export function TechBackdrop() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  useScrollVar(ref, !reduce);
  return (
    <div
      ref={ref}
      className="tech-backdrop"
      data-testid="tech-backdrop"
      data-reduced={reduce ? 'true' : 'false'}
      aria-hidden="true"
    />
  );
}

/** 页面顶部标题区：**装饰层**随滚动移动，内容层不动。
 *
 * 内容不动是刻意的：标题与按钮跟着滚动漂移会让人点不准，
 * 而这一层的目的只是让页面有纵深。 */
export function ParallaxHero({ title, subtitle, children }: {
  title: string; subtitle?: string; children?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  useScrollVar(ref, !reduce);
  return (
    <section ref={ref} className="hero" data-testid="parallax-hero"
             data-reduced={reduce ? 'true' : 'false'}>
      <div className="hero-layer" aria-hidden="true" />
      <div className="hero-content">
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
        {children}
      </div>
    </section>
  );
}

/** 进入视口时淡入 + 小位移（≤12px）。
 *
 * 一次性触发，不做「滚出去再淡出」那种来回动：那会让长列表在滚动时
 * 一直闪，而用户是来读内容的。 */
export function Reveal({ children, delayMs = 0 }: { children: ReactNode; delayMs?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (reduce) { setShown(true); return; }      // 直接到终态，不是动得少一点
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') { setShown(true); return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setShown(true);
        io.disconnect();                          // 一次性：触发完就不再观察
      }
    }, { rootMargin: '0px 0px -10% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, [reduce]);

  return (
    <div ref={ref} className={`reveal${shown ? ' in' : ''}`}
         style={delayMs && !reduce ? { transitionDelay: `${delayMs}ms` } : undefined}>
      {children}
    </div>
  );
}
