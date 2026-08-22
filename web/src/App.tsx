import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes } from 'react-router-dom';
import TabBar from './TabBar';
import Admin from './pages/Admin';
import Circles from './pages/Circles';
import Community from './pages/Community';
import Login from './pages/Login';
import Messages from './pages/Messages';
import Notifications from './pages/Notifications';
import Profile from './pages/Profile';
import Publish from './pages/Publish';
import Square from './pages/Square';
import Support from './pages/Support';
import TaskDetail from './pages/TaskDetail';
import WalletPage from './pages/Wallet';
import {
  dismissInstall,
  applyUpdate,
  promptInstall,
  registerServiceWorker,
  watchInstallPrompt,
} from './pwa';
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
      <nav className="nav">
        <Link className="logo" to="/">协作任务平台</Link>
        <Link to="/">任务广场</Link>
        <Link to="/publish">发布任务</Link>
        <Link to="/community">社区</Link>
        <Link to="/circles">圈层</Link>
        <Link to="/messages">消息</Link>
        <Link to="/wallet">钱包</Link>
        <Link to="/support">客服</Link>
        <span className="spacer" />
        {me ? (
          <>
            {me.is_admin && <Link to="/admin">管理</Link>}
            <Link className="nav-mobile-keep" to="/notifications">🔔</Link>
            <Link className="nav-mobile-keep" to="/profile">
              {me.nickname} <span className="badge">{me.credit_score} 分</span>
            </Link>
          </>
        ) : (
          <Link className="nav-mobile-keep" to="/login">登录 / 注册</Link>
        )}
      </nav>
      <Routes>
        <Route path="/" element={<Square />} />
        <Route path="/login" element={<Login />} />
        <Route path="/publish" element={hasToken ? <Publish /> : <Navigate to="/login" />} />
        <Route path="/tasks/:id" element={hasToken ? <TaskDetail /> : <Navigate to="/login" />} />
        <Route path="/wallet" element={hasToken ? <WalletPage /> : <Navigate to="/login" />} />
        <Route path="/community" element={hasToken ? <Community /> : <Navigate to="/login" />} />
        <Route path="/circles" element={hasToken ? <Circles /> : <Navigate to="/login" />} />
        <Route path="/messages" element={hasToken ? <Messages /> : <Navigate to="/login" />} />
        <Route path="/notifications" element={hasToken ? <Notifications /> : <Navigate to="/login" />} />
        <Route path="/profile" element={hasToken ? <Profile /> : <Navigate to="/login" />} />
        <Route path="/support" element={hasToken ? <Support /> : <Navigate to="/login" />} />
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
