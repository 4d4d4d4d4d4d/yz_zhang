import { Outlet, Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import useAuthStore from '../store/authStore';

const Layout = () => {
  const location = useLocation();
  const { user, logout } = useAuthStore();

  const navItems = [
    { path: '/', label: '首页', icon: '🏠' },
    { path: '/ai-companion', label: 'AI伴侣', icon: '🤖' },
    { path: '/matches', label: '匹配', icon: '💕' },
    { path: '/activities', label: '活动', icon: '🎯' },
    { path: '/games', label: '游戏', icon: '🎮' },
    { path: '/profile', label: '我的', icon: '👤' }
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* 顶部导航 */}
      <nav className="glass sticky top-0 z-50 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-center space-x-2">
            <span className="text-2xl">✨</span>
            <span className="text-xl font-bold gradient-text">神秘邂逅</span>
          </Link>

          <div className="flex items-center space-x-6">
            <span className="text-sm text-white/70">
              {user?.profile?.displayName || user?.username}
            </span>
            <button
              onClick={logout}
              className="text-sm text-white/70 hover:text-white transition-colors"
            >
              退出
            </button>
          </div>
        </div>
      </nav>

      {/* 主内容区 */}
      <main className="flex-1 overflow-y-auto pb-20">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          <Outlet />
        </motion.div>
      </main>

      {/* 底部导航 */}
      <nav className="fixed bottom-0 left-0 right-0 glass border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-around py-3">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className="flex flex-col items-center space-y-1 transition-all"
                >
                  <motion.div
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    className={`text-2xl ${
                      isActive ? 'filter drop-shadow-[0_0_8px_rgba(167,139,250,0.8)]' : ''
                    }`}
                  >
                    {item.icon}
                  </motion.div>
                  <span
                    className={`text-xs ${
                      isActive ? 'text-purple-300 font-semibold' : 'text-white/60'
                    }`}
                  >
                    {item.label}
                  </span>
                  {isActive && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute -bottom-3 w-12 h-1 bg-gradient-mystery rounded-full"
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>
    </div>
  );
};

export default Layout;
