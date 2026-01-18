import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import useAuthStore from './store/authStore';
import socketService from './services/socket';

// 页面组件
import Login from './pages/Login';
import Register from './pages/Register';
import Home from './pages/Home';
import AICompanion from './pages/AICompanion';
import Matches from './pages/Matches';
import Activities from './pages/Activities';
import ActivityDetail from './pages/ActivityDetail';
import Games from './pages/Games';
import Profile from './pages/Profile';
import Layout from './components/Layout';

// 受保护的路由
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? children : <Navigate to="/login" />;
};

function App() {
  const { isAuthenticated, user } = useAuthStore();

  useEffect(() => {
    // 如果用户已登录，连接Socket
    if (isAuthenticated && user) {
      socketService.connect(user._id);
    }

    return () => {
      // 清理Socket连接
      if (!isAuthenticated) {
        socketService.disconnect();
      }
    };
  }, [isAuthenticated, user]);

  return (
    <Router>
      <Routes>
        {/* 公开路由 */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* 受保护的路由 */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Home />} />
          <Route path="ai-companion" element={<AICompanion />} />
          <Route path="matches" element={<Matches />} />
          <Route path="activities" element={<Activities />} />
          <Route path="activities/:activityId" element={<ActivityDetail />} />
          <Route path="games" element={<Games />} />
          <Route path="profile" element={<Profile />} />
        </Route>

        {/* 重定向 */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
}

export default App;
