import { Link } from 'react-router-dom';
import { useApp } from '../store';

export default function Cooperate() {
  const { hasToken } = useApp();
  const target = (path: string) => hasToken ? path : `/login?next=${encodeURIComponent(path)}`;
  return <main className="page cooperation-home"><span className="overline">BUILD SOMETHING TOGETHER</span><h1>一起，把可能<br />变成日常。</h1><p className="cooperation-lead">一个小忙，一个新想法，或一件值得长久投入的事。</p><div className="cooperation-options">
    <Link to={target('/publish')} className="cooperation-option"><span className="overline">01 / 从想法开始</span><span className="cooperation-glyph">↗</span><h2>我想做一件事</h2><p>说出你的需要，让 AI 帮你梳理，再邀请合适的人。</p><span>发起合作 →</span></Link>
    <Link to="/opportunities" className="cooperation-option"><span className="overline">02 / 把能力带来</span><span className="cooperation-glyph">✳</span><h2>看看谁需要我</h2><p>在真实需求中，找到值得参与的事。</p><span>发现机会 →</span></Link>
    <Link to={target('/ventures')} className="cooperation-option"><span className="overline">03 / 长久地一起</span><span className="cooperation-glyph">◎</span><h2>一起经营一个未来</h2><p>聚起不同的能力，让合作持续生长。</p><span>进入合作体 →</span></Link>
  </div><div className="cooperation-tools"><Link to={target('/teams')}>团队与项目 ↗</Link><Link to={target('/wallet')}>收支与结算 ↗</Link><Link to="/records">协议与档案 ↗</Link><Link to="/chain">链上协作 ↗</Link><Link to={target('/profile')}>我的参与 ↗</Link></div></main>;
}
