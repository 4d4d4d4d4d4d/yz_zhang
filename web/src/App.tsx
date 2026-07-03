import { Link, Navigate, Route, Routes } from 'react-router-dom';
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
import { useApp } from './store';

export default function App() {
  const { me, hasToken } = useApp();
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
            <Link to="/notifications">🔔</Link>
            <Link to="/profile">
              {me.nickname} <span className="badge">{me.credit_score} 分</span>
            </Link>
          </>
        ) : (
          <Link to="/login">登录 / 注册</Link>
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
      </Routes>
    </>
  );
}
