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
import Discover from './pages/Discover';
import UserProfile from './pages/UserProfile';
import Settings from './pages/Settings';
import MatchDetail from './pages/MatchDetail';
import Moments from './pages/Moments';
import InteractiveGames from './pages/InteractiveGames';
import PartyRooms from './pages/PartyRooms';
import CreateGameRoom from './pages/CreateGameRoom';
import CreatePartyRoom from './pages/CreatePartyRoom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

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
    <ErrorBoundary>
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
            <Route path="matches/:matchId" element={<MatchDetail />} />
            <Route path="activities" element={<Activities />} />
            <Route path="activities/:activityId" element={<ActivityDetail />} />
            <Route path="games" element={<Games />} />
            <Route path="discover" element={<Discover />} />
            <Route path="users/:userId" element={<UserProfile />} />
            <Route path="moments" element={<Moments />} />
            <Route path="interactive-games" element={<InteractiveGames />} />
            <Route path="interactive-games/create" element={<CreateGameRoom />} />
            <Route path="party-rooms" element={<PartyRooms />} />
            <Route path="party-rooms/create" element={<CreatePartyRoom />} />
            <Route path="profile" element={<Profile />} />
            <Route path="settings" element={<Settings />} />
          </Route>

          {/* 重定向 */}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
