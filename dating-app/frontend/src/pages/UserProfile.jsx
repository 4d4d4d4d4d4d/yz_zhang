import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { userAPI, matchAPI, aiAPI, safetyAPI } from '../services/api';
import {
  ArrowLeftIcon,
  HeartIcon,
  ChatBubbleLeftRightIcon,
  MapPinIcon,
  CakeIcon,
  BriefcaseIcon,
  AcademicCapIcon,
  SparklesIcon,
  LightBulbIcon,
  EllipsisVerticalIcon,
  NoSymbolIcon,
  FlagIcon,
  XMarkIcon
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
  const [showMenu, setShowMenu] = useState(false);
  const [showBlockModal, setShowBlockModal] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [blockReason, setBlockReason] = useState('inappropriate');
  const [blockNotes, setBlockNotes] = useState('');
  const [reportReason, setReportReason] = useState('inappropriate_content');
  const [reportDescription, setReportDescription] = useState('');

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

  const handleBlock = async () => {
    try {
      await safetyAPI.blockUser(userId, {
        reason: blockReason,
        notes: blockNotes
      });
      alert('已屏蔽该用户');
      setShowBlockModal(false);
      navigate('/discover');
    } catch (error) {
      console.error('Block user error:', error);
      alert(error.response?.data?.error || '屏蔽失败，请重试');
    }
  };

  const handleReport = async () => {
    if (!reportDescription.trim()) {
      alert('请填写举报描述');
      return;
    }

    try {
      await safetyAPI.reportUser(userId, {
        type: 'user',
        reason: reportReason,
        description: reportDescription
      });
      alert('举报已提交，感谢您的反馈');
      setShowReportModal(false);
      setReportDescription('');
      setReportReason('inappropriate_content');
    } catch (error) {
      console.error('Report user error:', error);
      alert(error.response?.data?.error || '举报失败，请重试');
    }
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
          <div className="flex gap-3 items-center">
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

            {/* More Menu */}
            <div className="relative">
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="p-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-all"
              >
                <EllipsisVerticalIcon className="w-5 h-5" />
              </button>

              {showMenu && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="absolute right-0 mt-2 w-48 bg-gray-800 rounded-lg shadow-xl border border-white/10 overflow-hidden z-20"
                >
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowBlockModal(true);
                    }}
                    className="w-full px-4 py-3 text-left text-gray-300 hover:bg-white/10 transition-colors flex items-center gap-2"
                  >
                    <NoSymbolIcon className="w-5 h-5" />
                    屏蔽用户
                  </button>
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowReportModal(true);
                    }}
                    className="w-full px-4 py-3 text-left text-red-400 hover:bg-white/10 transition-colors flex items-center gap-2"
                  >
                    <FlagIcon className="w-5 h-5" />
                    举报用户
                  </button>
                </motion.div>
              )}
            </div>
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

      {/* Block Modal */}
      <AnimatePresence>
        {showBlockModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={() => setShowBlockModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="mystery-card p-6 max-w-md w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <NoSymbolIcon className="w-6 h-6 text-red-400" />
                  屏蔽用户
                </h2>
                <button
                  onClick={() => setShowBlockModal(false)}
                  className="text-gray-400 hover:text-white"
                >
                  <XMarkIcon className="w-6 h-6" />
                </button>
              </div>

              <p className="text-gray-300 mb-4">
                屏蔽后，您将无法看到该用户的信息，该用户也无法与您互动。
              </p>

              <div className="space-y-4">
                <div>
                  <label className="text-gray-300 text-sm mb-2 block">屏蔽原因</label>
                  <select
                    value={blockReason}
                    onChange={(e) => setBlockReason(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="harassment">骚扰</option>
                    <option value="inappropriate">不当行为</option>
                    <option value="spam">垃圾信息</option>
                    <option value="fake">虚假账号</option>
                    <option value="other">其他</option>
                  </select>
                </div>

                <div>
                  <label className="text-gray-300 text-sm mb-2 block">
                    备注（可选）
                  </label>
                  <textarea
                    value={blockNotes}
                    onChange={(e) => setBlockNotes(e.target.value)}
                    placeholder="添加备注..."
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                    rows={3}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowBlockModal(false)}
                  className="flex-1 px-4 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-all"
                >
                  取消
                </button>
                <button
                  onClick={handleBlock}
                  className="flex-1 px-4 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-all"
                >
                  确认屏蔽
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Report Modal */}
      <AnimatePresence>
        {showReportModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={() => setShowReportModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="mystery-card p-6 max-w-md w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <FlagIcon className="w-6 h-6 text-red-400" />
                  举报用户
                </h2>
                <button
                  onClick={() => setShowReportModal(false)}
                  className="text-gray-400 hover:text-white"
                >
                  <XMarkIcon className="w-6 h-6" />
                </button>
              </div>

              <p className="text-gray-300 mb-4">
                感谢您帮助我们维护社区安全。我们会认真审核您的举报。
              </p>

              <div className="space-y-4">
                <div>
                  <label className="text-gray-300 text-sm mb-2 block">举报原因</label>
                  <select
                    value={reportReason}
                    onChange={(e) => setReportReason(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="harassment">骚扰</option>
                    <option value="inappropriate_content">不当内容</option>
                    <option value="spam">垃圾信息</option>
                    <option value="fake_profile">虚假资料</option>
                    <option value="scam">诈骗</option>
                    <option value="underage">未成年</option>
                    <option value="violence">暴力内容</option>
                    <option value="hate_speech">仇恨言论</option>
                    <option value="other">其他</option>
                  </select>
                </div>

                <div>
                  <label className="text-gray-300 text-sm mb-2 block">
                    详细描述 <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    value={reportDescription}
                    onChange={(e) => setReportDescription(e.target.value)}
                    placeholder="请详细描述问题..."
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                    rows={4}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowReportModal(false)}
                  className="flex-1 px-4 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-all"
                >
                  取消
                </button>
                <button
                  onClick={handleReport}
                  className="flex-1 px-4 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-all"
                >
                  提交举报
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default UserProfile;
