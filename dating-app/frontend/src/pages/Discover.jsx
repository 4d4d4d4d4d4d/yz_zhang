import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { userAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  UserGroupIcon,
  GlobeAltIcon,
  MapPinIcon,
  FireIcon,
  FunnelIcon
} from '@heroicons/react/24/outline';
import { HeartIcon } from '@heroicons/react/24/solid';

const Discover = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('recommended');
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Search filters
  const [filters, setFilters] = useState({
    keyword: '',
    gender: '',
    minAge: '',
    maxAge: '',
    interests: '',
    city: ''
  });

  const tabs = [
    { id: 'recommended', label: '推荐', icon: HeartIcon, color: 'text-pink-500' },
    { id: 'search', label: '搜索', icon: MagnifyingGlassIcon, color: 'text-blue-500' },
    { id: 'online', label: '在线', icon: GlobeAltIcon, color: 'text-green-500' },
    { id: 'nearby', label: '附近', icon: MapPinIcon, color: 'text-purple-500' },
    { id: 'popular', label: '热门', icon: FireIcon, color: 'text-orange-500' }
  ];

  useEffect(() => {
    loadUsers();
  }, [activeTab]);

  const loadUsers = async () => {
    try {
      setLoading(true);
      let response;

      switch (activeTab) {
        case 'recommended':
          response = await userAPI.getRecommendedUsers(20);
          break;
        case 'search':
          response = await userAPI.searchUsers(filters);
          break;
        case 'online':
          response = await userAPI.getOnlineUsers(20);
          break;
        case 'nearby':
          response = await userAPI.getNearbyUsers(20);
          break;
        case 'popular':
          response = await userAPI.getPopularUsers(20);
          break;
        default:
          response = await userAPI.getRecommendedUsers(20);
      }

      setUsers(response.data.users || []);
    } catch (error) {
      console.error('Load users error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    if (activeTab !== 'search') {
      setActiveTab('search');
    } else {
      loadUsers();
    }
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const getCompatibilityColor = (score) => {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-blue-400';
    if (score >= 40) return 'text-yellow-400';
    return 'text-gray-400';
  };

  const getCompatibilityText = (score) => {
    if (score >= 80) return '超高匹配';
    if (score >= 60) return '高度匹配';
    if (score >= 40) return '中等匹配';
    return '一般匹配';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6">
      {/* Header */}
      <div className="max-w-6xl mx-auto mb-6">
        <h1 className="text-3xl font-bold text-white mb-6 flex items-center gap-3">
          <UserGroupIcon className="w-8 h-8 text-purple-400" />
          发现用户
        </h1>

        {/* Tabs */}
        <div className="flex gap-2 overflow-x-auto pb-2 mb-6">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-all ${
                  activeTab === tab.id
                    ? 'bg-purple-600 text-white shadow-lg'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                <Icon className={`w-5 h-5 ${activeTab === tab.id ? 'text-white' : tab.color}`} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="flex gap-3 mb-4">
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="搜索用户名或昵称..."
              value={filters.keyword}
              onChange={(e) => handleFilterChange('keyword', e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <MagnifyingGlassIcon className="absolute right-3 top-3.5 w-5 h-5 text-gray-400" />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-3 rounded-lg transition-all flex items-center gap-2 ${
              showFilters
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            <FunnelIcon className="w-5 h-5" />
            筛选
          </button>
          <button
            onClick={handleSearch}
            className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all"
          >
            搜索
          </button>
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mystery-card p-4 mb-4"
          >
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-gray-300 text-sm mb-2 block">性别</label>
                <select
                  value={filters.gender}
                  onChange={(e) => handleFilterChange('gender', e.target.value)}
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="">全部</option>
                  <option value="male">男</option>
                  <option value="female">女</option>
                  <option value="other">其他</option>
                </select>
              </div>

              <div>
                <label className="text-gray-300 text-sm mb-2 block">年龄范围</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="最小"
                    value={filters.minAge}
                    onChange={(e) => handleFilterChange('minAge', e.target.value)}
                    className="w-1/2 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <input
                    type="number"
                    placeholder="最大"
                    value={filters.maxAge}
                    onChange={(e) => handleFilterChange('maxAge', e.target.value)}
                    className="w-1/2 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-gray-300 text-sm mb-2 block">城市</label>
                <input
                  type="text"
                  placeholder="输入城市"
                  value={filters.city}
                  onChange={(e) => handleFilterChange('city', e.target.value)}
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="md:col-span-3">
                <label className="text-gray-300 text-sm mb-2 block">兴趣爱好（用逗号分隔）</label>
                <input
                  type="text"
                  placeholder="例如：旅行,摄影,音乐"
                  value={filters.interests}
                  onChange={(e) => handleFilterChange('interests', e.target.value)}
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Users Grid */}
      <div className="max-w-6xl mx-auto">
        {loading ? (
          <div className="text-center py-20">
            <div className="inline-block w-16 h-16 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="text-gray-400 mt-4">加载中...</p>
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-20">
            <UserGroupIcon className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">暂无用户</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {users.map((user) => (
              <motion.div
                key={user._id}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mystery-card overflow-hidden cursor-pointer hover:shadow-2xl transition-all"
                onClick={() => navigate(`/users/${user._id}`)}
              >
                {/* Profile Photo */}
                <div className="relative h-64 bg-gradient-to-br from-purple-600 to-pink-600">
                  {user.profile?.photos?.[0] ? (
                    <img
                      src={user.profile.photos[0]}
                      alt={user.profile.displayName}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <span className="text-6xl">
                        {user.profile?.aiAvatar?.emoji || '👤'}
                      </span>
                    </div>
                  )}

                  {/* Online Status */}
                  {user.isOnline && (
                    <div className="absolute top-4 right-4 px-3 py-1 bg-green-500 rounded-full text-white text-xs font-semibold flex items-center gap-1">
                      <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
                      在线
                    </div>
                  )}

                  {/* Compatibility Score */}
                  {user.compatibilityScore !== undefined && (
                    <div className="absolute bottom-4 left-4 px-3 py-1 bg-black/60 backdrop-blur-sm rounded-full">
                      <span className={`font-bold ${getCompatibilityColor(user.compatibilityScore)}`}>
                        {user.compatibilityScore}% {getCompatibilityText(user.compatibilityScore)}
                      </span>
                    </div>
                  )}
                </div>

                {/* User Info */}
                <div className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        {user.profile?.displayName || user.username}
                        {user.profile?.isVerified && (
                          <span className="text-blue-400 text-sm">✓</span>
                        )}
                      </h3>
                      <p className="text-gray-400 text-sm">
                        {user.profile?.age || '??'}岁 · {user.profile?.city || '未知'}
                      </p>
                    </div>
                  </div>

                  {/* Bio */}
                  {user.profile?.bio && (
                    <p className="text-gray-300 text-sm mb-3 line-clamp-2">
                      {user.profile.bio}
                    </p>
                  )}

                  {/* Interests */}
                  {user.profile?.interests && user.profile.interests.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-3">
                      {user.profile.interests.slice(0, 3).map((interest, index) => (
                        <span
                          key={index}
                          className="px-3 py-1 bg-purple-600/30 text-purple-300 text-xs rounded-full"
                        >
                          {interest}
                        </span>
                      ))}
                      {user.profile.interests.length > 3 && (
                        <span className="px-3 py-1 bg-white/10 text-gray-400 text-xs rounded-full">
                          +{user.profile.interests.length - 3}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Stats */}
                  <div className="flex items-center gap-4 text-xs text-gray-400 pt-3 border-t border-white/10">
                    <span>💕 {user.statistics?.totalMatches || 0} 匹配</span>
                    <span>🎯 {user.statistics?.activitiesParticipated || 0} 活动</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Discover;
