import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { notificationAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';

const NotificationBell = () => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadNotifications();
    loadUnreadCount();

    // 每30秒刷新一次未读数量
    const interval = setInterval(() => {
      loadUnreadCount();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const loadNotifications = async () => {
    try {
      setLoading(true);
      const res = await notificationAPI.getNotifications({ limit: 10 });
      setNotifications(res.data.notifications);
      setUnreadCount(res.data.unreadCount);
    } catch (error) {
      console.error('Failed to load notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadUnreadCount = async () => {
    try {
      const res = await notificationAPI.getUnreadCount();
      setUnreadCount(res.data.count);
    } catch (error) {
      console.error('Failed to load unread count:', error);
    }
  };

  const handleMarkAsRead = async (notificationId) => {
    try {
      await notificationAPI.markAsRead(notificationId);
      setNotifications(prev =>
        prev.map(n =>
          n._id === notificationId ? { ...n, isRead: true } : n
        )
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Failed to mark as read:', error);
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      await notificationAPI.markAllAsRead();
      setNotifications(prev =>
        prev.map(n => ({ ...n, isRead: true }))
      );
      setUnreadCount(0);
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const handleNotificationClick = (notification) => {
    // 标记为已读
    if (!notification.isRead) {
      handleMarkAsRead(notification._id);
    }

    // 跳转到相关页面
    if (notification.actionUrl) {
      navigate(notification.actionUrl);
    } else if (notification.relatedData) {
      const { matchId, activityId, gameId } = notification.relatedData;
      if (matchId) navigate(`/matches`);
      else if (activityId) navigate(`/activities`);
      else if (gameId) navigate(`/games`);
    }

    setShowDropdown(false);
  };

  const getNotificationIcon = (type) => {
    const icons = {
      new_match: '💕',
      match_accepted: '✨',
      new_message: '💬',
      activity_invite: '🎯',
      activity_reminder: '⏰',
      activity_update: '📢',
      game_invite: '🎮',
      game_turn: '🎲',
      profile_view: '👀',
      interest_match: '🌟',
      system: 'ℹ️'
    };
    return icons[type] || '🔔';
  };

  const getTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - new Date(date)) / 1000);

    if (seconds < 60) return '刚刚';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}天前`;
    return new Date(date).toLocaleDateString('zh-CN');
  };

  return (
    <div className="relative">
      {/* 通知铃铛按钮 */}
      <motion.button
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        onClick={() => setShowDropdown(!showDropdown)}
        className="relative p-2 rounded-full hover:bg-white/10 transition-colors"
      >
        <span className="text-2xl">🔔</span>
        {unreadCount > 0 && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-xs font-bold"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </motion.div>
        )}
      </motion.button>

      {/* 通知下拉面板 */}
      <AnimatePresence>
        {showDropdown && (
          <>
            {/* 遮罩层 */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowDropdown(false)}
            />

            {/* 下拉内容 */}
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="absolute right-0 mt-2 w-96 mystery-card z-50 max-h-[500px] overflow-hidden flex flex-col"
            >
              {/* 头部 */}
              <div className="flex items-center justify-between p-4 border-b border-white/10">
                <h3 className="font-semibold">通知</h3>
                {unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllAsRead}
                    className="text-sm text-purple-300 hover:text-purple-200"
                  >
                    全部标为已读
                  </button>
                )}
              </div>

              {/* 通知列表 */}
              <div className="flex-1 overflow-y-auto scrollbar-hide">
                {loading ? (
                  <div className="flex items-center justify-center p-8">
                    <div className="loader w-8 h-8" />
                  </div>
                ) : notifications.length === 0 ? (
                  <div className="text-center p-8 text-white/60">
                    <div className="text-4xl mb-2">📭</div>
                    <p>暂无通知</p>
                  </div>
                ) : (
                  <div className="divide-y divide-white/10">
                    {notifications.map((notification) => (
                      <motion.div
                        key={notification._id}
                        whileHover={{ backgroundColor: 'rgba(255, 255, 255, 0.05)' }}
                        onClick={() => handleNotificationClick(notification)}
                        className={`p-4 cursor-pointer transition-colors ${
                          !notification.isRead ? 'bg-white/5' : ''
                        }`}
                      >
                        <div className="flex items-start space-x-3">
                          {/* 图标 */}
                          <div className="text-2xl flex-shrink-0">
                            {getNotificationIcon(notification.type)}
                          </div>

                          {/* 内容 */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between">
                              <h4 className="font-semibold text-sm mb-1">
                                {notification.title}
                              </h4>
                              {!notification.isRead && (
                                <div className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0 ml-2 mt-1" />
                              )}
                            </div>
                            <p className="text-sm text-white/70 mb-1 line-clamp-2">
                              {notification.message}
                            </p>
                            <p className="text-xs text-white/50">
                              {getTimeAgo(notification.createdAt)}
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>

              {/* 底部 */}
              {notifications.length > 0 && (
                <div className="border-t border-white/10 p-3 text-center">
                  <button
                    onClick={() => {
                      navigate('/notifications');
                      setShowDropdown(false);
                    }}
                    className="text-sm text-purple-300 hover:text-purple-200"
                  >
                    查看全部通知 →
                  </button>
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default NotificationBell;
