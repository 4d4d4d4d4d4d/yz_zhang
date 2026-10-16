// APP-092 页面错误边界（183 号 spec）：一页渲染出错时只坏这一页，顶部导航还在，告诉人为什么、怎么办。
//
// 以前任何一页里一个 `.map` 碰上不是数组的响应，React 就把整棵树卸掉——用户看到的是白屏，连导航都没了，
// 只能关掉标签页。按路由加边界后：导航在、这一页换成一张说明卡；换一页（路径变了）边界自动复位。
import { Component, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    // 只记错误类型，不记内容：页面上的数据可能有个人信息（SEC-065）
    console.error('page_render_failed', error instanceof Error ? error.name : 'unknown');
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="page">
        <div className="card" role="alert" aria-label="这一页没加载出来">
          <h3>这一页没加载出来</h3>
          <p className="muted">可能是网络或服务暂时不正常。刷新一下再试；一直这样，请到「客服」提单，写上是哪一页。</p>
          <div className="row">
            <button onClick={() => window.location.reload()}>刷新</button>
            <Link to="/support">去客服</Link>
          </div>
        </div>
      </div>
    );
  }
}

/** 按路径复位：从出错的页面点到别的页，新页面正常显示。 */
export default function RouteBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Boundary key={pathname}>{children}</Boundary>;
}
