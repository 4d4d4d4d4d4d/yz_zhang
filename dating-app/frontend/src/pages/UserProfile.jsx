import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { userAPI, matchAPI, aiAPI } from '../services/api';
import {
  ArrowLeftIcon,
  HeartIcon,
  ChatBubbleLeftRightIcon,
  MapPinIcon,
  CakeIcon,
  BriefcaseIcon,
  AcademicCapIcon,
  SparklesIcon,
  LightBulbIcon
} from '@heroicons/react/24/outline';
import { HeartIcon as HeartSolidIcon } from '@heroicons/react/24/solid';

const UserProfile = () => {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [iceBreakers, setIceBreakers] = useState([]);
  const [showIceBreakers, setShowIceBreakers] = useState(false);

  useEffect(() => {
    loadUserProfile();
    loadIceBreakers();
  }, [userId]);

  const loadUserProfile = async () => {
    try {
      setLoading(true);
      const response = await userAPI.getUserProfile(userId);
      setUser(response.data.user);
    } catch (error) {
      console.error('Load user profile error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadIceBreakers = async () => {
    try {
      const response = await aiAPI.generateIceBreakers(userId);
      setIceBreakers(response.data.iceBreakers || []);
    } catch (error) {
      console.error('Load ice breakers error:', error);
    }
  };

  const handleMatch = async () => {
    try {
      setMatching(true);
      await matchAPI.createMatch(userId);
      alert('匹配请求已发送！');
    } catch (error) {
      console.error('Match error:', error);
      alert(error.response?.data?.error || '匹配失败，请重试');
    } finally {
      setMatching(false);
    }
  };

  const handleChat = () => {
    // Navigate to chat page with this user
    navigate(`/chat/${userId}`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block w-16 h-16 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-gray-400 mt-4">加载中...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 text-lg">用户不存在</p>
          <button
            onClick={() => navigate('/discover')}
            className="mt-4 px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            返回发现页
          </button>
        </div>
      </div>
    );
  }

  const profile = user.profile || {};

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
          <div className="flex gap-3">
            <button
              onClick={handleChat}
              className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-all flex items-center gap-2"
            >
              <ChatBubbleLeftRightIcon className="w-5 h-5" />
              聊天
            </button>
            <button
              onClick={handleMatch}
              disabled={matching}
              className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {matching ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  发送中...
                </>
              ) : (
                <>
                  <HeartSolidIcon className="w-5 h-5" />
                  发起匹配
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Profile Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mystery-card p-8 mb-6"
        >
          <div className="flex flex-col md:flex-row gap-6">
            {/* Avatar */}
            <div className="flex-shrink-0">
              <div className="w-32 h-32 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center overflow-hidden">
                {profile.photos?.[0] ? (
                  <img
                    src={profile.photos[0]}
                    alt={profile.displayName}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-6xl">
                    {profile.aiAvatar?.emoji || '👤'}
                  </span>
                )}
              </div>
              {user.isOnline && (
                <div className="mt-2 text-center text-green-400 text-sm flex items-center justify-center gap-1">
                  <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                  在线
                </div>
              )}
            </div>

            {/* Basic Info */}
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-2">
                {profile.displayName || user.username}
                {profile.isVerified && (
                  <span className="text-blue-400 text-lg">✓</span>
                )}
              </h1>

              <div className="flex flex-wrap gap-4 text-gray-300 mb-4">
                {profile.age && (
                  <div className="flex items-center gap-2">
                    <CakeIcon className="w-5 h-5 text-purple-400" />
                    {profile.age}岁
                  </div>
                )}
                {profile.gender && (
                  <div className="flex items-center gap-2">
                    <span className="text-purple-400">
                      {profile.gender === 'male' ? '👨' : profile.gender === 'female' ? '👩' : '🧑'}
                    </span>
                    {profile.gender === 'male' ? '男' : profile.gender === 'female' ? '女' : '其他'}
                  </div>
                )}
                {profile.city && (
                  <div className="flex items-center gap-2">
                    <MapPinIcon className="w-5 h-5 text-purple-400" />
                    {profile.city}
                  </div>
                )}
              </div>

              {profile.bio && (
                <p className="text-gray-300 mb-4">{profile.bio}</p>
              )}

              {/* Stats */}
              <div className="flex gap-6 text-sm">
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-400">
                    {user.statistics?.totalMatches || 0}
                  </div>
                  <div className="text-gray-400">匹配数</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-pink-400">
                    {user.statistics?.activitiesParticipated || 0}
                  </div>
                  <div className="text-gray-400">参与活动</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-400">
                    {user.statistics?.gamesPlayed || 0}
                  </div>
                  <div className="text-gray-400">游戏次数</div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* AI Avatar Personality */}
        {profile.aiAvatar && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mystery-card p-6 mb-6"
          >
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <SparklesIcon className="w-6 h-6 text-yellow-400" />
              AI性格画像
            </h2>
            <div className="flex items-start gap-4">
              <div className="text-6xl">{profile.aiAvatar.emoji}</div>
              <div>
                <h3 className="text-lg font-semibold text-purple-300 mb-2">
                  {profile.aiAvatar.personality}
                </h3>
                <p className="text-gray-300">{profile.aiAvatar.description}</p>
              </div>
            </div>
          </motion.div>
        )}

        {/* Interests */}
        {profile.interests && profile.interests.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="mystery-card p-6 mb-6"
          >
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <HeartIcon className="w-6 h-6 text-pink-400" />
              兴趣爱好
            </h2>
            <div className="flex flex-wrap gap-3">
              {profile.interests.map((interest, index) => (
                <span
                  key={index}
                  className="px-4 py-2 bg-gradient-to-r from-purple-600/30 to-pink-600/30 text-purple-300 rounded-full border border-purple-500/30"
                >
                  {interest}
                </span>
              ))}
            </div>
          </motion.div>
        )}

        {/* Career & Education */}
        {(profile.occupation || profile.education) && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mystery-card p-6 mb-6"
          >
            <h2 className="text-xl font-bold text-white mb-4">职业与教育</h2>
            <div className="space-y-3">
              {profile.occupation && (
                <div className="flex items-center gap-3 text-gray-300">
                  <BriefcaseIcon className="w-5 h-5 text-purple-400" />
                  <span>{profile.occupation}</span>
                </div>
              )}
              {profile.education && (
                <div className="flex items-center gap-3 text-gray-300">
                  <AcademicCapIcon className="w-5 h-5 text-purple-400" />
                  <span>{profile.education}</span>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Ice Breakers */}
        {iceBreakers.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mystery-card p-6"
          >
            <button
              onClick={() => setShowIceBreakers(!showIceBreakers)}
              className="w-full flex items-center justify-between text-xl font-bold text-white mb-4"
            >
              <div className="flex items-center gap-2">
                <LightBulbIcon className="w-6 h-6 text-yellow-400" />
                AI破冰话题建议
              </div>
              <span className="text-gray-400">
                {showIceBreakers ? '收起' : '展开'}
              </span>
            </button>

            {showIceBreakers && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="space-y-3"
              >
                {iceBreakers.map((breaker, index) => (
                  <div
                    key={index}
                    className="p-4 bg-white/5 rounded-lg border border-white/10 hover:border-purple-500/50 transition-all"
                  >
                    <p className="text-gray-300">{breaker}</p>
                  </div>
                ))}
              </motion.div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default UserProfile;
