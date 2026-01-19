import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { momentAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  HeartIcon,
  ChatBubbleLeftIcon,
  ShareIcon,
  EllipsisHorizontalIcon,
  PlusIcon,
  FireIcon,
  MapPinIcon,
  FaceSmileIcon,
  PhotoIcon,
  PencilSquareIcon
} from '@heroicons/react/24/outline';
import { HeartIcon as HeartSolidIcon } from '@heroicons/react/24/solid';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';

const Moments = () => {
  const navigate = useNavigate();
  const [moments, setMoments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [trendingTopics, setTrendingTopics] = useState([]);
  const [activeTab, setActiveTab] = useState('feed');
  const [showCreateModal, setShowCreateModal] = useState(false);

  useEffect(() => {
    loadMoments();
    loadTrendingTopics();
  }, [activeTab]);

  const loadMoments = async () => {
    try {
      setLoading(true);
      const params = activeTab === 'nearby' ? { longitude: 0, latitude: 0 } : {};
      const response = activeTab === 'nearby'
        ? await momentAPI.getNearbyMoments(params)
        : await momentAPI.getMomentsFeed(params);
      setMoments(response.data.moments || []);
    } catch (error) {
      console.error('Load moments error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadTrendingTopics = async () => {
    try {
      const response = await momentAPI.getTrendingTopics({ limit: 10 });
      setTrendingTopics(response.data.topics || []);
    } catch (error) {
      console.error('Load trending topics error:', error);
    }
  };

  const handleLike = async (momentId) => {
    try {
      await momentAPI.toggleLike(momentId);
      setMoments(prev => prev.map(m => {
        if (m._id === momentId) {
          const liked = !m.likes.some(l => l.user._id === m.currentUserId);
          return {
            ...m,
            likes: liked
              ? [...m.likes, { user: { _id: m.currentUserId } }]
              : m.likes.filter(l => l.user._id !== m.currentUserId)
          };
        }
        return m;
      }));
    } catch (error) {
      console.error('Toggle like error:', error);
    }
  };

  const handleComment = async (momentId, content) => {
    try {
      await momentAPI.addComment(momentId, { content });
      await loadMoments();
    } catch (error) {
      console.error('Add comment error:', error);
    }
  };

  const renderMomentCard = (moment) => {
    const isLiked = moment.likes?.some(l => l.user?._id === moment.currentUserId);

    return (
      <motion.div
        key={moment._id}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mystery-card p-6 mb-4"
      >
        {/* User Header */}
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center cursor-pointer"
            onClick={() => navigate(`/users/${moment.user._id}`)}
          >
            {moment.user.profile?.photos?.[0] ? (
              <img
                src={moment.user.profile.photos[0]}
                alt={moment.user.profile.displayName}
                className="w-full h-full rounded-full object-cover"
              />
            ) : (
              <span className="text-2xl">
                {moment.user.profile?.aiAvatar?.emoji || '👤'}
              </span>
            )}
          </div>
          <div className="flex-1">
            <h3 className="text-white font-semibold">
              {moment.anonymous ? '神秘用户' : (moment.user.profile?.displayName || moment.user.username)}
            </h3>
            <p className="text-gray-400 text-sm">
              {new Date(moment.createdAt).toLocaleString()}
            </p>
          </div>
          <button className="text-gray-400 hover:text-white">
            <EllipsisHorizontalIcon className="w-6 h-6" />
          </button>
        </div>

        {/* Mood */}
        {moment.mood && (
          <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-white/5 rounded-lg inline-flex">
            <span className="text-2xl">{moment.mood.emoji}</span>
            <span className="text-gray-300 text-sm">{moment.mood.label}</span>
          </div>
        )}

        {/* Content */}
        {moment.content?.text && (
          <p className="text-gray-200 mb-4 whitespace-pre-wrap">{moment.content.text}</p>
        )}

        {/* Images */}
        {moment.content?.images && moment.content.images.length > 0 && (
          <div className={`grid gap-2 mb-4 ${
            moment.content.images.length === 1 ? 'grid-cols-1' :
            moment.content.images.length === 2 ? 'grid-cols-2' :
            'grid-cols-3'
          }`}>
            {moment.content.images.map((img, idx) => (
              <img
                key={idx}
                src={img}
                alt="moment"
                className="w-full h-48 object-cover rounded-lg"
              />
            ))}
          </div>
        )}

        {/* Poll */}
        {moment.type === 'poll' && moment.poll && (
          <div className="mb-4 space-y-2">
            <h4 className="text-white font-semibold mb-3">{moment.poll.question}</h4>
            {moment.poll.options.map((option, idx) => (
              <button
                key={idx}
                className="w-full text-left px-4 py-3 bg-white/10 rounded-lg hover:bg-white/20 transition-all"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-200">{option.text}</span>
                  <span className="text-purple-400">{option.votes?.length || 0}票</span>
                </div>
                <div className="w-full bg-white/5 rounded-full h-2">
                  <div
                    className="bg-purple-600 h-full rounded-full transition-all"
                    style={{
                      width: `${(option.votes?.length || 0) / Math.max(1, moment.poll.options.reduce((sum, o) => sum + (o.votes?.length || 0), 0)) * 100}%`
                    }}
                  />
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Location */}
        {moment.location?.name && (
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-4">
            <MapPinIcon className="w-4 h-4" />
            {moment.location.name}
          </div>
        )}

        {/* Tags */}
        {moment.tags && moment.tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {moment.tags.map((tag, idx) => (
              <span key={idx} className="px-3 py-1 bg-purple-600/30 text-purple-300 text-sm rounded-full">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-6 pt-4 border-t border-white/10">
          <button
            onClick={() => handleLike(moment._id)}
            className="flex items-center gap-2 text-gray-300 hover:text-pink-400 transition-colors"
          >
            {isLiked ? (
              <HeartSolidIcon className="w-6 h-6 text-pink-500" />
            ) : (
              <HeartIcon className="w-6 h-6" />
            )}
            <span>{moment.likes?.length || 0}</span>
          </button>

          <button className="flex items-center gap-2 text-gray-300 hover:text-blue-400 transition-colors">
            <ChatBubbleLeftIcon className="w-6 h-6" />
            <span>{moment.comments?.length || 0}</span>
          </button>

          <button className="flex items-center gap-2 text-gray-300 hover:text-green-400 transition-colors">
            <ShareIcon className="w-6 h-6" />
            <span>{moment.shares?.length || 0}</span>
          </button>

          <div className="flex-1"></div>

          <span className="text-gray-500 text-sm">
            {moment.views || 0} 浏览
          </span>
        </div>

        {/* Comments Preview */}
        {moment.comments && moment.comments.length > 0 && (
          <div className="mt-4 pt-4 border-t border-white/10 space-y-3">
            {moment.comments.slice(0, 2).map((comment) => (
              <div key={comment._id} className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center text-sm flex-shrink-0">
                  {comment.user.profile?.aiAvatar?.emoji || '👤'}
                </div>
                <div className="flex-1">
                  <span className="text-purple-300 font-semibold text-sm">
                    {comment.user.profile?.displayName || comment.user.username}
                  </span>
                  <p className="text-gray-300 text-sm mt-1">{comment.content}</p>
                </div>
              </div>
            ))}
            {moment.comments.length > 2 && (
              <button className="text-purple-400 text-sm hover:underline">
                查看全部 {moment.comments.length} 条评论
              </button>
            )}
          </div>
        )}
      </motion.div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6 pb-24">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <FaceSmileIcon className="w-8 h-8 text-purple-400" />
            瞬间
          </h1>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center gap-2"
          >
            <PlusIcon className="w-5 h-5" />
            发布瞬间
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Feed */}
          <div className="lg:col-span-2">
            {/* Tabs */}
            <div className="flex gap-2 mb-6 overflow-x-auto">
              {[
                { id: 'feed', label: '推荐', icon: FireIcon },
                { id: 'nearby', label: '附近', icon: MapPinIcon }
              ].map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-all ${
                      activeTab === tab.id
                        ? 'bg-purple-600 text-white'
                        : 'bg-white/10 text-gray-300 hover:bg-white/20'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Moments List */}
            {loading ? (
              <Loading message="加载瞬间..." />
            ) : moments.length === 0 ? (
              <EmptyState
                icon={FaceSmileIcon}
                title="暂无瞬间"
                description="成为第一个分享瞬间的人吧！"
                action={() => setShowCreateModal(true)}
                actionLabel="发布瞬间"
              />
            ) : (
              moments.map(renderMomentCard)
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Trending Topics */}
            <div className="mystery-card p-6">
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <FireIcon className="w-6 h-6 text-orange-400" />
                热门话题
              </h2>
              <div className="space-y-3">
                {trendingTopics.map((topic, idx) => (
                  <button
                    key={idx}
                    className="w-full text-left px-4 py-3 bg-white/5 rounded-lg hover:bg-white/10 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-purple-300">#{topic.topic}</span>
                      <span className="text-gray-400 text-sm">{topic.count}条</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="mystery-card p-6">
              <h2 className="text-xl font-bold text-white mb-4">快捷操作</h2>
              <div className="space-y-2">
                <button className="w-full px-4 py-3 bg-white/10 rounded-lg hover:bg-white/20 transition-all flex items-center gap-2">
                  <PhotoIcon className="w-5 h-5 text-purple-400" />
                  <span className="text-gray-200">分享照片</span>
                </button>
                <button className="w-full px-4 py-3 bg-white/10 rounded-lg hover:bg-white/20 transition-all flex items-center gap-2">
                  <PencilSquareIcon className="w-5 h-5 text-pink-400" />
                  <span className="text-gray-200">写下心情</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Moments;
