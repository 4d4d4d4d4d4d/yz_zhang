import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { activityAPI } from '../services/api';
import useAuthStore from '../store/authStore';

const ActivityDetail = () => {
  const { activityId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [activity, setActivity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadActivity();
  }, [activityId]);

  const loadActivity = async () => {
    try {
      setLoading(true);
      const res = await activityAPI.getActivityDetails(activityId);
      setActivity(res.data);
    } catch (error) {
      console.error('Failed to load activity:', error);
      alert('加载活动失败');
    } finally {
      setLoading(false);
    }
  };

  const handleJoin = async () => {
    try {
      setActionLoading(true);
      await activityAPI.joinActivity(activityId);
      alert('报名成功！');
      loadActivity();
    } catch (error) {
      alert(error.response?.data?.error || '报名失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleLeave = async () => {
    if (!confirm('确定要取消报名吗？')) return;

    try {
      setActionLoading(true);
      await activityAPI.leaveActivity(activityId);
      alert('已取消报名');
      loadActivity();
    } catch (error) {
      alert(error.response?.data?.error || '取消失败');
    } finally {
      setActionLoading(false);
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
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="loader" />
      </div>
    );
  }

  if (!activity) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="mystery-card p-12 text-center">
          <div className="text-6xl mb-4">❌</div>
          <h2 className="text-2xl font-bold mb-2">活动不存在</h2>
          <button
            onClick={() => navigate('/activities')}
            className="mystery-button mt-4"
          >
            返回活动列表
          </button>
        </div>
      </div>
    );
  }

  const isParticipating = activity.participants?.current?.some(
    p => p.user?._id === user?._id
  );

  const confirmedParticipants = activity.participants?.current?.filter(
    p => p.status === 'confirmed'
  ) || [];

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* 返回按钮 */}
      <motion.button
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center space-x-2 text-white/70 hover:text-white transition-colors"
      >
        <span className="text-2xl">←</span>
        <span>返回</span>
      </motion.button>

      <div className="grid md:grid-cols-3 gap-6">
        {/* 主要信息 */}
        <div className="md:col-span-2 space-y-6">
          {/* 活动封面 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mystery-card overflow-hidden"
          >
            <div className="h-64 bg-gradient-mystery rounded-t-2xl flex items-center justify-center text-8xl relative">
              <div className="absolute inset-0 bg-black/30" />
              <span className="relative z-10">{getActivityIcon(activity.type)}</span>

              {activity.mysteryMode?.enabled && (
                <div className="absolute top-4 right-4 badge bg-purple-500/80 backdrop-blur-sm">
                  🔮 神秘盲盒
                </div>
              )}

              {activity.status === 'full' && (
                <div className="absolute bottom-4 left-4 badge bg-red-500/80 backdrop-blur-sm">
                  已满员
                </div>
              )}
            </div>

            <div className="p-6">
              <div className="badge mb-4">{activity.type}</div>
              <h1 className="text-3xl font-bold mb-4">{activity.title}</h1>
              <p className="text-white/80 text-lg leading-relaxed">
                {activity.description}
              </p>
            </div>
          </motion.div>

          {/* 活动详情 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mystery-card"
          >
            <h2 className="text-xl font-bold mb-4">活动详情</h2>

            <div className="space-y-4">
              <div className="flex items-start space-x-3">
                <span className="text-2xl">📅</span>
                <div>
                  <div className="text-white/70 text-sm">时间</div>
                  <div className="font-semibold">{formatDate(activity.schedule.startTime)}</div>
                  <div className="text-white/60 text-sm">
                    预计 {activity.schedule.duration} 分钟
                  </div>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <span className="text-2xl">📍</span>
                <div>
                  <div className="text-white/70 text-sm">地点</div>
                  <div className="font-semibold">{activity.location?.name}</div>
                  <div className="text-white/60 text-sm">{activity.location?.address}</div>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <span className="text-2xl">👥</span>
                <div>
                  <div className="text-white/70 text-sm">参与人数</div>
                  <div className="font-semibold">
                    {confirmedParticipants.length} / {activity.participants?.max} 人
                  </div>
                  <div className="text-white/60 text-sm">
                    最少 {activity.participants?.min} 人
                  </div>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <span className="text-2xl">💰</span>
                <div>
                  <div className="text-white/70 text-sm">费用</div>
                  <div className="font-semibold">
                    {activity.cost?.amount === 0 ? '免费' : `¥${activity.cost?.amount}`}
                  </div>
                  {activity.cost?.includes && activity.cost.includes.length > 0 && (
                    <div className="text-white/60 text-sm">
                      包含：{activity.cost.includes.join('、')}
                    </div>
                  )}
                </div>
              </div>

              {activity.difficulty && (
                <div className="flex items-start space-x-3">
                  <span className="text-2xl">⚡</span>
                  <div>
                    <div className="text-white/70 text-sm">难度</div>
                    <div className="font-semibold">
                      {activity.difficulty === 'easy' && '简单'}
                      {activity.difficulty === 'moderate' && '中等'}
                      {activity.difficulty === 'challenging' && '挑战'}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {activity.tags && activity.tags.length > 0 && (
              <div className="mt-6">
                <div className="flex flex-wrap gap-2">
                  {activity.tags.map((tag) => (
                    <span key={tag} className="badge">
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </motion.div>

          {/* 神秘惊喜 */}
          {activity.mysteryMode?.enabled && activity.mysteryMode?.surpriseElement && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="mystery-card bg-gradient-mystery/20"
            >
              <div className="flex items-center space-x-3 mb-3">
                <span className="text-2xl">🎁</span>
                <h3 className="font-bold">神秘惊喜</h3>
              </div>
              <p className="text-white/80">{activity.mysteryMode.surpriseElement}</p>
            </motion.div>
          )}
        </div>

        {/* 侧边栏 */}
        <div className="space-y-6">
          {/* 操作按钮 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mystery-card"
          >
            {isParticipating ? (
              <button
                onClick={handleLeave}
                disabled={actionLoading}
                className="w-full py-3 rounded-xl bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 transition-all disabled:opacity-50"
              >
                {actionLoading ? '处理中...' : '取消报名'}
              </button>
            ) : (
              <button
                onClick={handleJoin}
                disabled={actionLoading || activity.status === 'full'}
                className="w-full mystery-button disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? '处理中...' :
                 activity.status === 'full' ? '已满员' : '立即报名'}
              </button>
            )}
          </motion.div>

          {/* 组织者 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mystery-card"
          >
            <h3 className="font-bold mb-4">组织者</h3>
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 rounded-full bg-gradient-mystery flex items-center justify-center text-2xl">
                👤
              </div>
              <div>
                <div className="font-semibold">
                  {activity.organizer?.username}
                </div>
                <div className="text-sm text-white/60">活动组织者</div>
              </div>
            </div>
          </motion.div>

          {/* 参与者列表 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="mystery-card"
          >
            <h3 className="font-bold mb-4">
              参与者 ({confirmedParticipants.length})
            </h3>

            {confirmedParticipants.length === 0 ? (
              <p className="text-white/60 text-sm text-center py-4">
                还没有人报名
              </p>
            ) : (
              <div className="space-y-3 max-h-64 overflow-y-auto scrollbar-hide">
                {confirmedParticipants.map((participant) => {
                  const showInfo = !activity.mysteryMode?.enabled ||
                    new Date() >= new Date(activity.mysteryMode.revealTime);

                  return (
                    <div key={participant._id} className="flex items-center space-x-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-mystery flex items-center justify-center flex-shrink-0">
                        {showInfo ? (
                          participant.user?.username?.[0] || '?'
                        ) : (
                          '?'
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">
                          {showInfo ?
                            participant.user?.username :
                            `神秘参与者 #${participant._id.slice(-4)}`
                          }
                        </div>
                        {participant.user?._id === user?._id && (
                          <div className="text-xs text-purple-300">你</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>

          {/* 平均评分 */}
          {activity.feedback && activity.feedback.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              className="mystery-card"
            >
              <h3 className="font-bold mb-4">活动评价</h3>
              <div className="text-center">
                <div className="text-4xl font-bold gradient-text mb-2">
                  {activity.averageRating || '0.0'}
                </div>
                <div className="text-sm text-white/60">
                  {activity.feedback.length} 条评价
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ActivityDetail;
