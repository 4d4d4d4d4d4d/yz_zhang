import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { activityAPI } from '../services/api';

const Activities = () => {
  const [activities, setActivities] = useState([]);
  const [recommendedActivities, setRecommendedActivities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('all'); // all, recommended, joined

  useEffect(() => {
    loadActivities();
    loadRecommendedActivities();
  }, []);

  const loadActivities = async () => {
    try {
      setLoading(true);
      const res = await activityAPI.getActivities({ limit: 20 });
      setActivities(res.data.activities);
    } catch (error) {
      console.error('Failed to load activities:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadRecommendedActivities = async () => {
    try {
      const res = await activityAPI.getRecommendedActivities(6);
      setRecommendedActivities(res.data.activities);
    } catch (error) {
      console.error('Failed to load recommended activities:', error);
    }
  };

  const handleJoinActivity = async (activityId) => {
    try {
      await activityAPI.joinActivity(activityId);
      loadActivities();
      alert('报名成功！');
    } catch (error) {
      alert(error.response?.data?.error || '报名失败');
    }
  };

  const getActivityIcon = (type) => {
    const icons = {
      camping: '🏕️',
      'cafe-hopping': '☕',
      museum: '🏛️',
      'escape-room': '🔐',
      'team-building': '🤝',
      hiking: '🥾',
      concert: '🎵',
      'cooking-class': '👨‍🍳',
      'art-gallery': '🎨',
      sports: '⚽',
      movie: '🎬',
      karaoke: '🎤',
      'board-games': '🎲',
      'wine-tasting': '🍷',
      'photography-walk': '📷'
    };
    return icons[type] || '🎯';
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const displayActivities = view === 'recommended' ? recommendedActivities : activities;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      {/* 顶部 */}
      <div className="text-center">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <h1 className="text-3xl font-bold gradient-text mb-2">活动广场</h1>
          <p className="text-white/60">发现有趣的线下活动，邂逅志同道合的人</p>
        </motion.div>
      </div>

      {/* 视图切换 */}
      <div className="flex space-x-4">
        <button
          onClick={() => setView('all')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'all' ? 'bg-gradient-mystery' : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          全部活动
        </button>
        <button
          onClick={() => setView('recommended')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'recommended' ? 'bg-gradient-mystery' : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          推荐活动
        </button>
      </div>

      {/* 活动列表 */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="loader" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {displayActivities.length === 0 ? (
            <div className="col-span-full mystery-card p-12 text-center">
              <div className="text-6xl mb-4">🎯</div>
              <h3 className="text-2xl font-bold mb-2">暂无活动</h3>
              <p className="text-white/60">敬请期待更多精彩活动</p>
            </div>
          ) : (
            displayActivities.map((activity, index) => (
              <motion.div
                key={activity._id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className="activity-card"
              >
                {/* 活动封面 */}
                <div className="h-48 bg-gradient-mystery rounded-t-2xl flex items-center justify-center text-6xl relative overflow-hidden">
                  <div className="absolute inset-0 bg-black/30" />
                  <span className="relative z-10">{getActivityIcon(activity.type)}</span>

                  {/* 神秘模式标记 */}
                  {activity.mysteryMode?.enabled && (
                    <div className="absolute top-4 right-4 badge bg-purple-500/80 backdrop-blur-sm">
                      🔮 神秘盲盒
                    </div>
                  )}

                  {/* 状态标记 */}
                  {activity.status === 'full' && (
                    <div className="absolute bottom-4 left-4 badge bg-red-500/80 backdrop-blur-sm">
                      已满员
                    </div>
                  )}
                </div>

                {/* 活动信息 */}
                <div className="p-6 space-y-4">
                  <div>
                    <div className="badge mb-2 text-xs">{activity.type}</div>
                    <h3 className="text-lg font-bold mb-2 line-clamp-1">
                      {activity.title}
                    </h3>
                    <p className="text-sm text-white/70 line-clamp-2">
                      {activity.description}
                    </p>
                  </div>

                  {/* 详细信息 */}
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center space-x-2 text-white/60">
                      <span>📅</span>
                      <span>{formatDate(activity.schedule.startTime)}</span>
                    </div>
                    <div className="flex items-center space-x-2 text-white/60">
                      <span>📍</span>
                      <span className="line-clamp-1">
                        {activity.location?.name || activity.location?.city}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-white/60">
                      <div className="flex items-center space-x-2">
                        <span>👥</span>
                        <span>
                          {activity.participants?.current?.length || 0} / {activity.participants?.max}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span>💰</span>
                        <span>
                          {activity.cost?.amount === 0 ? '免费' : `¥${activity.cost?.amount}`}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 标签 */}
                  {activity.tags && activity.tags.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {activity.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="badge text-xs">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* 操作按钮 */}
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleJoinActivity(activity._id)}
                    disabled={activity.status === 'full' || activity.isParticipating}
                    className="w-full mystery-button text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {activity.isParticipating ? '已报名' :
                     activity.status === 'full' ? '已满员' : '立即报名'}
                  </motion.button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      )}

      {/* 创建活动按钮 */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="fixed bottom-24 right-6"
      >
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          className="w-14 h-14 rounded-full bg-gradient-mystery shadow-2xl flex items-center justify-center text-2xl"
          title="创建活动"
        >
          ➕
        </motion.button>
      </motion.div>
    </div>
  );
};

export default Activities;
