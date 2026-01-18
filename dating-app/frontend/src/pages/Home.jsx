import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import useAuthStore from '../store/authStore';
import { matchAPI, activityAPI } from '../services/api';

const Home = () => {
  const { user } = useAuthStore();
  const [recommendations, setRecommendations] = useState([]);
  const [randomActivity, setRandomActivity] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHomeData();
  }, []);

  const loadHomeData = async () => {
    try {
      setLoading(true);
      // 获取推荐匹配
      const matchRes = await matchAPI.getRecommendations({ limit: 3, mysteryMode: true });
      setRecommendations(matchRes.data.recommendations);

      // 获取随机活动
      try {
        const activityRes = await activityAPI.getRandomActivity();
        setRandomActivity(activityRes.data.activity);
      } catch (err) {
        console.log('No random activity available');
      }
    } catch (error) {
      console.error('Failed to load home data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRandomActivity = async () => {
    try {
      const res = await activityAPI.getRandomActivity();
      setRandomActivity(res.data.activity);
    } catch (error) {
      console.error('Failed to get random activity:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="loader" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      {/* 欢迎横幅 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mystery-card text-center py-12 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-mystery opacity-20" />
        <div className="relative z-10">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
            className="inline-block text-6xl mb-4"
          >
            ✨
          </motion.div>
          <h1 className="text-3xl font-bold gradient-text mb-2">
            欢迎回来，{user?.profile?.displayName || user?.username}
          </h1>
          <p className="text-white/70">今天会有怎样的神秘邂逅呢？</p>
        </div>
      </motion.div>

      {/* 快速操作 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { icon: '🤖', label: 'AI伴侣', desc: '情感陪伴', link: '/ai-companion', color: 'from-purple-500 to-pink-500' },
          { icon: '💕', label: '寻找匹配', desc: '神秘邂逅', link: '/matches', color: 'from-pink-500 to-red-500' },
          { icon: '🎯', label: '活动广场', desc: '线下聚会', link: '/activities', color: 'from-blue-500 to-cyan-500' },
          { icon: '🎮', label: '互动游戏', desc: '趣味互动', link: '/games', color: 'from-orange-500 to-yellow-500' },
          { icon: '👤', label: '个人资料', desc: '完善信息', link: '/profile', color: 'from-green-500 to-teal-500' }
        ].map((item, index) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
            whileHover={{ scale: 1.05 }}
          >
            <Link to={item.link} className="block mystery-card hover-lift text-center">
              <div className={`w-16 h-16 mx-auto mb-3 rounded-2xl bg-gradient-to-br ${item.color} flex items-center justify-center text-3xl`}>
                {item.icon}
              </div>
              <h3 className="font-semibold mb-1">{item.label}</h3>
              <p className="text-sm text-white/60">{item.desc}</p>
            </Link>
          </motion.div>
        ))}
      </div>

      {/* 推荐匹配 */}
      {recommendations.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold gradient-text">为你推荐</h2>
            <Link to="/matches" className="text-sm text-purple-300 hover:text-purple-200">
              查看更多 →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {recommendations.map((rec, index) => (
              <motion.div
                key={rec.user._id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className="mystery-card hover-lift cursor-pointer"
              >
                <div className="relative">
                  {/* AI化身 */}
                  <div className="w-full h-48 bg-gradient-mystery rounded-xl mb-4 flex items-center justify-center text-6xl relative overflow-hidden">
                    <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
                    <span className="relative z-10">👤</span>
                    <div className="absolute top-2 right-2 badge text-xs">
                      匹配度 {rec.compatibility}%
                    </div>
                  </div>

                  {/* 神秘信息 */}
                  <div className="space-y-2">
                    <h3 className="font-semibold text-lg">神秘人 #{rec.user._id.slice(-4)}</h3>
                    <p className="text-sm text-white/60 line-clamp-2">
                      {rec.user.profile?.bio || '一个充满神秘感的灵魂...'}
                    </p>

                    {/* 部分兴趣 */}
                    {rec.user.interests && (
                      <div className="flex flex-wrap gap-2">
                        {rec.user.interests.slice(0, 3).map((interest) => (
                          <span key={interest} className="badge text-xs">
                            {interest}
                          </span>
                        ))}
                        <span className="badge text-xs">???</span>
                      </div>
                    )}

                    {/* 破冰话题 */}
                    {rec.iceBreakers && rec.iceBreakers[0] && (
                      <div className="mt-3 p-3 bg-white/5 rounded-lg">
                        <p className="text-xs text-white/50 mb-1">💡 破冰话题</p>
                        <p className="text-sm text-white/80">{rec.iceBreakers[0]}</p>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* 神秘活动盲盒 */}
      {randomActivity && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mystery-card relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-cosmic opacity-20 rounded-full blur-3xl" />
          <div className="relative z-10">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold gradient-text mb-2">🎁 神秘活动盲盒</h2>
                <p className="text-white/60">随机为你推荐一个神秘活动</p>
              </div>
              <motion.button
                whileHover={{ scale: 1.1, rotate: 180 }}
                whileTap={{ scale: 0.9 }}
                onClick={handleRandomActivity}
                className="text-3xl"
              >
                🎲
              </motion.button>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <div className="badge mb-2">{randomActivity.type}</div>
                  <h3 className="text-xl font-semibold mb-2">{randomActivity.title}</h3>
                  <p className="text-white/70">{randomActivity.description}</p>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center space-x-2">
                    <span>📍</span>
                    <span className="text-white/70">
                      {randomActivity.location?.name || randomActivity.location?.city}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span>👥</span>
                    <span className="text-white/70">
                      {randomActivity.participants?.current?.length || 0} / {randomActivity.participants?.max} 人
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span>💰</span>
                    <span className="text-white/70">
                      {randomActivity.cost?.amount === 0 ? '免费' : `¥${randomActivity.cost?.amount}`}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-center">
                <Link
                  to={`/activities`}
                  className="mystery-button w-full text-center"
                >
                  查看活动详情
                </Link>
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'AI对话', value: user?.stats?.aiConversations || 0, icon: '💬' },
          { label: '匹配数', value: user?.stats?.matches || 0, icon: '💕' },
          { label: '活动参与', value: user?.stats?.activitiesAttended || 0, icon: '🎯' },
          { label: '游戏次数', value: user?.stats?.gamesPlayed || 0, icon: '🎮' }
        ].map((stat) => (
          <div key={stat.label} className="mystery-card text-center">
            <div className="text-3xl mb-2">{stat.icon}</div>
            <div className="text-2xl font-bold gradient-text mb-1">{stat.value}</div>
            <div className="text-sm text-white/60">{stat.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Home;
