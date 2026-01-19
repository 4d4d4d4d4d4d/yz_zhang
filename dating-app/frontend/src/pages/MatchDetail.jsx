import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { matchAPI } from '../services/api';
import Loading from '../components/Loading';
import {
  ArrowLeftIcon,
  HeartIcon,
  ChatBubbleLeftRightIcon,
  SparklesIcon,
  LockClosedIcon,
  LockOpenIcon,
  CalendarIcon,
  FireIcon,
  CheckCircleIcon,
  XCircleIcon
} from '@heroicons/react/24/outline';

const MatchDetail = () => {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const [match, setMatch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [revealing, setRevealing] = useState(false);

  useEffect(() => {
    loadMatchDetails();
  }, [matchId]);

  const loadMatchDetails = async () => {
    try {
      setLoading(true);
      const response = await matchAPI.getMatchDetails(matchId);
      setMatch(response.data.match);
    } catch (error) {
      console.error('Load match details error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRevealInfo = async () => {
    try {
      setRevealing(true);
      await matchAPI.revealMysteryInfo(matchId);
      await loadMatchDetails(); // Reload to get updated info
    } catch (error) {
      console.error('Reveal info error:', error);
      alert(error.response?.data?.error || '揭示信息失败');
    } finally {
      setRevealing(false);
    }
  };

  const handleChat = () => {
    const otherUser = match.user1._id === match.currentUserId ? match.user2 : match.user1;
    navigate(`/chat/${otherUser._id}`);
  };

  if (loading) {
    return <Loading fullScreen message="加载匹配详情..." />;
  }

  if (!match) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 text-lg mb-4">匹配不存在</p>
          <button
            onClick={() => navigate('/matches')}
            className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            返回匹配列表
          </button>
        </div>
      </div>
    );
  }

  const otherUser = match.user1._id === match.currentUserId ? match.user2 : match.user1;
  const profile = otherUser.profile || {};
  const compatibility = match.compatibility || {};
  const mysteryStage = match.mysteryMode?.revealStage || 0;
  const maxStage = 5;
  const revealProgress = (mysteryStage / maxStage) * 100;

  // Compatibility breakdown
  const compatibilityDetails = [
    { label: '兴趣匹配', score: compatibility.interests || 0, icon: '🎨', color: 'text-purple-400' },
    { label: '性格契合', score: compatibility.personality || 0, icon: '✨', color: 'text-pink-400' },
    { label: '活动偏好', score: compatibility.activities || 0, icon: '🎯', color: 'text-blue-400' },
    { label: '情绪同步', score: compatibility.emotionalSync || 0, icon: '💝', color: 'text-red-400' }
  ];

  const getScoreColor = (score) => {
    if (score >= 80) return 'bg-green-500';
    if (score >= 60) return 'bg-blue-500';
    if (score >= 40) return 'bg-yellow-500';
    return 'bg-gray-500';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 pb-20">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-black/30 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5" />
            返回
          </button>
          <button
            onClick={handleChat}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center gap-2"
          >
            <ChatBubbleLeftRightIcon className="w-5 h-5" />
            开始聊天
          </button>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Match Status */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mystery-card p-6 mb-6 text-center"
        >
          <div className="flex justify-center mb-4">
            {match.status === 'accepted' ? (
              <CheckCircleIcon className="w-16 h-16 text-green-400" />
            ) : match.status === 'rejected' ? (
              <XCircleIcon className="w-16 h-16 text-red-400" />
            ) : (
              <HeartIcon className="w-16 h-16 text-purple-400 animate-pulse" />
            )}
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">
            {match.status === 'accepted' && '匹配成功！'}
            {match.status === 'pending' && '等待回应'}
            {match.status === 'rejected' && '匹配未成功'}
          </h2>
          <p className="text-gray-400">
            于 {new Date(match.createdAt).toLocaleDateString()} 创建
          </p>
        </motion.div>

        {/* User Profile Summary */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mystery-card p-6 mb-6"
        >
          <div className="flex items-center gap-6">
            <div className="w-24 h-24 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center text-4xl overflow-hidden flex-shrink-0">
              {profile.photos?.[0] ? (
                <img src={profile.photos[0]} alt={profile.displayName} className="w-full h-full object-cover" />
              ) : (
                <span>{profile.aiAvatar?.emoji || '👤'}</span>
              )}
            </div>
            <div className="flex-1">
              <h3 className="text-2xl font-bold text-white mb-2">
                {profile.displayName || otherUser.username}
              </h3>
              {profile.age && <p className="text-gray-400">{profile.age}岁</p>}
              {profile.bio && <p className="text-gray-300 mt-2">{profile.bio}</p>}
            </div>
          </div>
        </motion.div>

        {/* Compatibility Score */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mystery-card p-6 mb-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <HeartIcon className="w-6 h-6 text-pink-400" />
            匹配度分析
          </h2>

          <div className="text-center mb-6">
            <div className="relative inline-block">
              <svg className="w-32 h-32 transform -rotate-90">
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  className="text-white/10"
                />
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="url(#gradient)"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${2 * Math.PI * 56}`}
                  strokeDashoffset={`${2 * Math.PI * 56 * (1 - match.compatibilityScore / 100)}`}
                  className="transition-all duration-1000"
                />
                <defs>
                  <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#a855f7" />
                    <stop offset="100%" stopColor="#ec4899" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <div>
                  <div className="text-4xl font-bold text-white">{match.compatibilityScore}%</div>
                  <div className="text-sm text-gray-400">总分</div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {compatibilityDetails.map((detail, index) => (
              <motion.div
                key={detail.label}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + index * 0.1 }}
                className="bg-white/5 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{detail.icon}</span>
                    <span className="text-gray-300 text-sm">{detail.label}</span>
                  </div>
                  <span className={`font-bold ${detail.color}`}>{detail.score}%</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2">
                  <div
                    className={`h-full rounded-full ${getScoreColor(detail.score)} transition-all duration-1000`}
                    style={{ width: `${detail.score}%` }}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Mystery Mode */}
        {match.mysteryMode?.enabled && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mystery-card p-6 mb-6"
          >
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <SparklesIcon className="w-6 h-6 text-yellow-400" />
              神秘模式进度
            </h2>

            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-300">解锁进度</span>
                <span className="text-white font-semibold">阶段 {mysteryStage}/{maxStage}</span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-3">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-purple-600 to-pink-600 transition-all duration-1000"
                  style={{ width: `${revealProgress}%` }}
                />
              </div>
            </div>

            {match.mysteryMode.unlockedInfo && match.mysteryMode.unlockedInfo.length > 0 && (
              <div className="mb-4">
                <h3 className="text-white font-semibold mb-2">已解锁信息：</h3>
                <div className="flex flex-wrap gap-2">
                  {match.mysteryMode.unlockedInfo.map((info, index) => (
                    <span
                      key={index}
                      className="px-3 py-1 bg-green-600/30 text-green-300 rounded-full text-sm flex items-center gap-1"
                    >
                      <LockOpenIcon className="w-4 h-4" />
                      {info}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {mysteryStage < maxStage && (
              <button
                onClick={handleRevealInfo}
                disabled={revealing}
                className="w-full px-4 py-3 bg-gradient-to-r from-yellow-600 to-orange-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {revealing ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    揭示中...
                  </>
                ) : (
                  <>
                    <LockClosedIcon className="w-5 h-5" />
                    揭示更多信息
                  </>
                )}
              </button>
            )}
          </motion.div>
        )}

        {/* Interaction Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mystery-card p-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <FireIcon className="w-6 h-6 text-orange-400" />
            互动统计
          </h2>

          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-3xl font-bold text-purple-400">
                {match.interactions?.messages || 0}
              </div>
              <div className="text-gray-400 text-sm">消息数</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-pink-400">
                {match.interactions?.games || 0}
              </div>
              <div className="text-gray-400 text-sm">游戏次数</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-blue-400">
                {match.interactions?.activities || 0}
              </div>
              <div className="text-gray-400 text-sm">共同活动</div>
            </div>
          </div>

          {match.lastInteraction && (
            <div className="mt-4 pt-4 border-t border-white/10 text-center">
              <div className="flex items-center justify-center gap-2 text-gray-400 text-sm">
                <CalendarIcon className="w-4 h-4" />
                最后互动：{new Date(match.lastInteraction).toLocaleString()}
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
};

export default MatchDetail;
