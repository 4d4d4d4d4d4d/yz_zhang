import { lazy, Suspense, useEffect, useState } from 'react';
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import TabBar from './TabBar';
import Admin from './pages/Admin';
import Circles from './pages/Circles';
import Community from './pages/Community';
import Login from './pages/Login';
import Messages from './pages/Messages';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import Publish from './pages/Publish';
import Decompose from './pages/Decompose';
import Rewards from './pages/Rewards';
import Square from './pages/Square';
import { Discover, PublicSpace, EditSpace, FollowList } from './pages/Spaces';
import Cooperate from './pages/Cooperate';
import Ask from './pages/Ask';
import Search from './pages/Search';
import Support from './pages/Support';
import TaskDetail from './pages/TaskDetail';
import Developer from './pages/Developer';
import Teams from './pages/Teams';
import Ventures from './pages/Ventures';
import Verify from './pages/Verify';
import Workbench from './pages/Workbench';
import Notebook from './pages/Notebook';
import Packs from './pages/Packs';
const Chain = lazy(() => import('./pages/Chain'));
const Records = lazy(() => import('./pages/Records'));
import WalletPage from './pages/Wallet';
import {
  dismissInstall,
  applyUpdate,
  promptInstall,
  registerServiceWorker,
  watchInstallPrompt,
} from './pwa';
import { TechBackdrop } from './Motion';
import { useApp } from './store';

export default function App() {
  const { me, hasToken } = useApp();
  // MOB-013/014 PWA：新版本提示与安装引导
  const [hasUpdate, setHasUpdate] = useState(false);
  const [canInstall, setCanInstall] = useState(false);
  useEffect(() => {
    registerServiceWorker(() => setHasUpdate(true));
    watchInstallPrompt(() => setCanInstall(true));
  }, []);

  return (
    <>
      {/* UI-090 全站固定背景（79 号 spec）：只有一个实例，纯装饰、不吃指针事件 */}
      <TechBackdrop />
      {import.meta.env.VITE_DEPLOYMENT_LABEL && (
        <aside className="deployment-notice" role="status">
          {import.meta.env.VITE_DEPLOYMENT_LABEL}
        </aside>
      )}
      <nav className="nav" aria-label="工作台导航">
        <Link className="logo" to="/"><span className="brand-mark" aria-hidden="true">o.</span><span>OPC<small>人与可能</small></span></Link>
        <div className="nav-links">
          {[['/','发现'],['/cooperate','合作'],['/workbench','工作台'],['/notebook','知识库'],['/packs','服务包'],['/messages','消息'],['/space/edit','我的空间']].map(([to,label]) => <NavLink key={to} end={to==='/'} to={to}>{label}</NavLink>)}
        </div>
        <span className="spacer" />
        {me ? <div className="nav-account">
          {me.is_admin && <Link to="/admin">管理</Link>}
          <Link className="nav-mobile-keep" to="/search" aria-label="搜索">⌕</Link>
          <Link className="nav-mobile-keep" to="/notifications" aria-label="通知">🔔</Link>
          <Link className="nav-mobile-keep" to="/profile">{me.nickname}<small>账户</small></Link>
        </div> : <Link className="nav-mobile-keep nav-signin" to="/login">登录 / 注册 <span aria-hidden="true">→</span></Link>}
        <details className="mobile-menu"><summary>全部功能</summary><div>{[['/opportunities','合作机会'],['/community','社区'],['/circles','圈层'],['/ventures','合作体'],['/teams','团队'],['/wallet','钱包'],['/chain','链上协作'],['/records','企业档案'],['/rewards','优惠'],['/verify','核验台'],['/developer','开发者'],['/ask','不懂就问'],['/support','客服']].map(([to,label])=><Link key={to} to={to}>{label}</Link>)}</div></details>
      </nav>
      <Routes>
        <Route path="/" element={<Discover />} />
        <Route path="/opportunities" element={<Square />} />
        <Route path="/cooperate" element={<Cooperate />} />
        <Route path="/people/:id" element={<PublicSpace />} />
        {/* CNT-023 关注 / 粉丝列表：公开的人的列表未登录也能看，与公开空间同一口径 */}
        <Route path="/people/:id/follows" element={<FollowList />} />
        <Route path="/space/edit" element={hasToken ? <EditSpace /> : <Navigate to="/login?next=/space/edit" />} />
        <Route path="/login" element={<Login />} />
        <Route path="/records" element={<Suspense fallback={<div className="page">正在加载企业档案…</div>}><Records /></Suspense>} />
        <Route path="/chain" element={<Suspense fallback={<div className="page">正在加载链上协作…</div>}><Chain /></Suspense>} />
        <Route path="/publish" element={hasToken ? <Publish /> : <Navigate to="/login" />} />
        <Route path="/tasks/:id" element={hasToken ? <TaskDetail /> : <Navigate to="/login" />} />
        {/* AI-DEC-041 逐层拆解：拆到一半关掉页面，回来接着拆 */}
        <Route path="/tasks/:id/decompose" element={hasToken ? <Decompose /> : <Navigate to="/login" />} />
        <Route path="/wallet" element={hasToken ? <WalletPage /> : <Navigate to="/login" />} />
        <Route path="/community" element={hasToken ? <Community /> : <Navigate to="/login" />} />
        <Route path="/circles" element={hasToken ? <Circles /> : <Navigate to="/login" />} />
        <Route path="/messages" element={hasToken ? <Messages /> : <Navigate to="/login" />} />
        <Route path="/workbench" element={hasToken ? <Workbench /> : <Navigate to="/login?next=/workbench" />} />
        {/* KB-100 个人知识库：门户 = 助手 + 知识库（122 号 spec） */}
        <Route path="/notebook" element={hasToken ? <Notebook /> : <Navigate to="/login?next=/notebook" />} />
        {/* PACK-100 服务包：助手专家 + 做法 + 知识 + 提醒，一键启用（123 号 spec） */}
        <Route path="/packs" element={hasToken ? <Packs /> : <Navigate to="/login?next=/packs" />} />
        <Route path="/notifications" element={hasToken ? <Notifications /> : <Navigate to="/login" />} />
        <Route path="/profile" element={hasToken ? <Profile /> : <Navigate to="/login" />} />
        <Route path="/rewards" element={hasToken ? <Rewards /> : <Navigate to="/login" />} />
        <Route path="/ask" element={hasToken ? <Ask /> : <Navigate to="/login?next=/ask" />} />
        {/* SRCH-001 全站搜索（V127）。结果接口要登录（搜索记录按人去重），热词与联想不要 */}
        <Route path="/search" element={hasToken ? <Search /> : <Navigate to="/login?next=/search" />} />
        <Route path="/support" element={hasToken ? <Support /> : <Navigate to="/login" />} />
        <Route path="/verify" element={hasToken ? <Verify /> : <Navigate to="/login" />} />
        <Route path="/ventures" element={hasToken ? <Ventures /> : <Navigate to="/login" />} />
        <Route path="/teams" element={hasToken ? <Teams /> : <Navigate to="/login" />} />
        <Route path="/developer" element={hasToken ? <Developer /> : <Navigate to="/login" />} />
        <Route path="/admin" element={hasToken ? <Admin /> : <Navigate to="/login" />} />
      </Routes>

      {canInstall && (
        <div className="install-tip">
          <span className="grow">把「协作任务平台」添加到主屏幕，用起来像个 App。</span>
          <button onClick={() => void promptInstall().then(() => setCanInstall(false))}>添加</button>
          <button className="ghost" onClick={() => { dismissInstall(); setCanInstall(false); }}>
            不了
          </button>
        </div>
      )}

      {hasUpdate && (
        <div className="update-tip" role="status">
          <span>有新版本可用</span>
          <button onClick={applyUpdate}>刷新</button>
        </div>
      )}

      <TabBar />
    </>
  );
}
