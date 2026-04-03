import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { matchAPI } from '../services/api';

const Matches = () => {
  const [view, setView] = useState('discover'); // discover, my-matches
  const [recommendations, setRecommendations] = useState([]);
  const [myMatches, setMyMatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (view === 'discover') {
      loadRecommendations();
    } else {
      loadMyMatches();
    }
  }, [view]);

  const loadRecommendations = async () => {
    try {
      setLoading(true);
      const res = await matchAPI.getRecommendations({ limit: 10, mysteryMode: true });
      setRecommendations(res.data.recommendations);
      setCurrentIndex(0);
    } catch (error) {
      console.error('Failed to load recommendations:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadMyMatches = async () => {
    try {
      setLoading(true);
      const res = await matchAPI.getMyMatches();
      setMyMatches(res.data.matches);
    } catch (error) {
      console.error('Failed to load matches:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSwipe = async (direction) => {
    if (currentIndex >= recommendations.length) return;

    const currentRec = recommendations[currentIndex];

    if (direction === 'right') {
      // 喜欢 - 创建匹配
      try {
        await matchAPI.createMatch(currentRec.user._id);
      } catch (error) {
        console.error('Failed to create match:', error);
      }
    }

    // 移到下一个
    setCurrentIndex(prev => prev + 1);

    // 如果到最后了，重新加载
    if (currentIndex >= recommendations.length - 3) {
      loadRecommendations();
    }
  };

  const currentCard = recommendations[currentIndex];

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      {/* 顶部标签切换 */}
      <div className="flex space-x-4 mb-6">
        <button
          onClick={() => setView('discover')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'discover'
              ? 'bg-gradient-mystery'
              : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          发现新人
        </button>
        <button
          onClick={() => setView('my-matches')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'my-matches'
              ? 'bg-gradient-mystery'
              : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          我的匹配
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="loader" />
        </div>
      ) : view === 'discover' ? (
        // 发现模式 - 卡片滑动
        <div className="relative h-[70vh] flex items-center justify-center">
          <AnimatePresence>
            {currentCard ? (
              <motion.div
                key={currentIndex}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                onDragEnd={(e, { offset, velocity }) => {
                  const swipe = Math.abs(offset.x) * velocity.x;
                  if (swipe < -10000) {
                    handleSwipe('left');
                  } else if (swipe > 10000) {
                    handleSwipe('right');
                  }
                }}
                className="w-full max-w-md"
              >
                <div className="mystery-card p-8">
                  {/* 神秘头像 */}
                  <div className="relative mb-6">
                    <div className="w-full aspect-square bg-gradient-mystery rounded-2xl flex items-center justify-center text-9xl relative overflow-hidden">
                      <div className="absolute inset-0 bg-black/40 backdrop-blur-md" />
                      <span className="relative z-10">👤</span>
                      <div className="absolute top-4 right-4 badge">
                        匹配度 {currentCard.compatibility}%
                      </div>
                    </div>
                  </div>

                  {/* 信息 */}
                  <div className="space-y-4">
                    <div>
                      <h2 className="text-2xl font-bold mb-2">
                        神秘人 #{currentCard.user._id.slice(-4)}
                      </h2>
                      <p className="text-white/70">
                        {currentCard.user.profile?.bio || '一个充满神秘的灵魂...'}
                      </p>
                    </div>

                    {/* 兴趣标签 */}
                    {currentCard.user.interests && (
                      <div className="flex flex-wrap gap-2">
                        {currentCard.user.interests.map((interest) => (
                          <span key={interest} className="badge">
                            {interest}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* 兼容性分析 */}
                    <div className="grid grid-cols-2 gap-3 p-4 bg-white/5 rounded-xl">
                      <div>
                        <div className="text-xs text-white/50 mb-1">兴趣匹配</div>
                        <div className="text-lg font-semibold gradient-text">
                          {currentCard.breakdown?.interests}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-white/50 mb-1">性格契合</div>
                        <div className="text-lg font-semibold gradient-text">
                          {currentCard.breakdown?.personality}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-white/50 mb-1">活动偏好</div>
                        <div className="text-lg font-semibold gradient-text">
                          {currentCard.breakdown?.activities}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-white/50 mb-1">情绪同步</div>
                        <div className="text-lg font-semibold gradient-text">
                          {currentCard.breakdown?.emotionalSync}%
                        </div>
                      </div>
                    </div>

                    {/* 破冰话题 */}
                    {currentCard.iceBreakers && currentCard.iceBreakers[0] && (
                      <div className="p-4 bg-purple-500/20 rounded-xl border border-purple-400/30">
                        <div className="text-xs text-white/50 mb-2">💡 AI推荐破冰话题</div>
                        <p className="text-white/90">{currentCard.iceBreakers[0]}</p>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mystery-card p-12 text-center"
              >
                <div className="text-6xl mb-4">✨</div>
                <h3 className="text-2xl font-bold mb-2">暂无更多推荐</h3>
                <p className="text-white/60 mb-6">稍后再来看看新的缘分吧</p>
                <button
                  onClick={loadRecommendations}
                  className="mystery-button"
                >
                  重新加载
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* 操作按钮 */}
          {currentCard && (
            <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 flex space-x-6">
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => handleSwipe('left')}
                className="w-16 h-16 rounded-full bg-white/10 hover:bg-red-500/30 border-2 border-red-500/50 flex items-center justify-center text-2xl transition-all"
              >
                ✖️
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => handleSwipe('right')}
                className="w-16 h-16 rounded-full bg-white/10 hover:bg-green-500/30 border-2 border-green-500/50 flex items-center justify-center text-2xl transition-all"
              >
                💕
              </motion.button>
            </div>
          )}
        </div>
      ) : (
        // 我的匹配列表
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {myMatches.length === 0 ? (
            <div className="col-span-full mystery-card p-12 text-center">
              <div className="text-6xl mb-4">💔</div>
              <h3 className="text-2xl font-bold mb-2">还没有匹配</h3>
              <p className="text-white/60 mb-6">去发现页面寻找你的缘分吧</p>
              <button
                onClick={() => setView('discover')}
                className="mystery-button"
              >
                开始探索
              </button>
            </div>
          ) : (
            myMatches.map((match) => (
              <motion.div
                key={match._id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="mystery-card hover-lift cursor-pointer"
              >
                <div className="flex items-center space-x-4 mb-4">
                  <div className="w-16 h-16 rounded-full bg-gradient-mystery flex items-center justify-center text-3xl">
                    👤
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold">神秘匹配</h3>
                    <p className="text-sm text-white/60">
                      匹配度 {match.compatibility?.overall}%
                    </p>
                  </div>
                  <div className={`badge ${
                    match.status === 'accepted' ? 'bg-green-500/20' :
                    match.status === 'pending' ? 'bg-yellow-500/20' :
                    'bg-gray-500/20'
                  }`}>
                    {match.status === 'accepted' ? '已匹配' :
                     match.status === 'pending' ? '等待中' :
                     match.status}
                  </div>
                </div>

                <div className="text-sm text-white/70 mb-4">
                  {match.interactions?.messages || 0} 条消息
                </div>

                {match.mysteryMode?.enabled && (
                  <div className="flex items-center space-x-2 text-sm text-purple-300">
                    <span>🔒</span>
                    <span>神秘等级 {match.mysteryMode.revealStage}/5</span>
                  </div>
                )}
              </motion.div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default Matches;
