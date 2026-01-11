import { useState } from 'react';
import { motion } from 'framer-motion';
import useAuthStore from '../store/authStore';
import { authAPI } from '../services/api';

const Profile = () => {
  const { user, updateUser } = useAuthStore();
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    profile: user?.profile || {},
    interests: user?.interests || [],
    aiAvatar: user?.aiAvatar || {}
  });
  const [loading, setLoading] = useState(false);

  const interestOptions = [
    { value: 'travel', label: '旅行', icon: '✈️' },
    { value: 'reading', label: '阅读', icon: '📚' },
    { value: 'movies', label: '电影', icon: '🎬' },
    { value: 'music', label: '音乐', icon: '🎵' },
    { value: 'sports', label: '运动', icon: '⚽' },
    { value: 'gaming', label: '游戏', icon: '🎮' },
    { value: 'cooking', label: '烹饪', icon: '🍳' },
    { value: 'art', label: '艺术', icon: '🎨' },
    { value: 'photography', label: '摄影', icon: '📷' },
    { value: 'dancing', label: '舞蹈', icon: '💃' },
    { value: 'hiking', label: '徒步', icon: '🥾' },
    { value: 'yoga', label: '瑜伽', icon: '🧘' }
  ];

  const handleSave = async () => {
    try {
      setLoading(true);
      const res = await authAPI.updateProfile(formData);
      updateUser(res.data.user);
      setIsEditing(false);
      alert('保存成功！');
    } catch (error) {
      alert('保存失败：' + (error.response?.data?.error || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  const toggleInterest = (interest) => {
    setFormData({
      ...formData,
      interests: formData.interests.includes(interest)
        ? formData.interests.filter(i => i !== interest)
        : [...formData.interests, interest]
    });
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      {/* 个人资料卡片 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mystery-card"
      >
        <div className="flex items-center space-x-6 mb-6">
          {/* 头像 */}
          <div className="w-24 h-24 rounded-full bg-gradient-mystery flex items-center justify-center text-5xl">
            {user?.profile?.photos?.[0] ? (
              <img
                src={user.profile.photos[0].url}
                alt="avatar"
                className="w-full h-full rounded-full object-cover"
              />
            ) : (
              <span>👤</span>
            )}
          </div>

          {/* 基本信息 */}
          <div className="flex-1">
            <h2 className="text-2xl font-bold mb-1">
              {user?.profile?.displayName || user?.username}
            </h2>
            <p className="text-white/60 mb-2">
              {user?.profile?.age}岁 · {user?.profile?.gender === 'male' ? '男' : user?.profile?.gender === 'female' ? '女' : '其他'}
            </p>
            <div className="flex space-x-2">
              <span className="badge">{user?.membership?.type || 'free'} 会员</span>
              {user?.isVerified && (
                <span className="badge bg-green-500/20">已认证</span>
              )}
            </div>
          </div>

          {/* 编辑按钮 */}
          <button
            onClick={() => setIsEditing(!isEditing)}
            className="px-6 py-2 rounded-full bg-white/10 hover:bg-white/20 transition-all"
          >
            {isEditing ? '取消' : '编辑'}
          </button>
        </div>

        {/* 简介 */}
        {isEditing ? (
          <textarea
            value={formData.profile.bio || ''}
            onChange={(e) =>
              setFormData({
                ...formData,
                profile: { ...formData.profile, bio: e.target.value }
              })
            }
            className="mystery-input min-h-[100px]"
            placeholder="介绍一下自己..."
          />
        ) : (
          <p className="text-white/80 mb-4">
            {user?.profile?.bio || '这个人很神秘，什么都没有留下...'}
          </p>
        )}

        {/* 保存按钮 */}
        {isEditing && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSave}
            disabled={loading}
            className="w-full mystery-button mt-4"
          >
            {loading ? '保存中...' : '保存更改'}
          </motion.button>
        )}
      </motion.div>

      {/* AI化身设置 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mystery-card"
      >
        <h3 className="text-xl font-bold mb-4 gradient-text">AI化身设置</h3>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-white/80">
              性格类型
            </label>
            <select
              value={formData.aiAvatar.personality || 'mysterious'}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  aiAvatar: { ...formData.aiAvatar, personality: e.target.value }
                })
              }
              disabled={!isEditing}
              className="mystery-input"
            >
              <option value="mysterious">神秘</option>
              <option value="cheerful">开朗</option>
              <option value="intellectual">睿智</option>
              <option value="adventurous">冒险</option>
              <option value="artistic">艺术</option>
              <option value="calm">沉静</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-white/80">
              语音风格
            </label>
            <select
              value={formData.aiAvatar.voiceTone || 'warm'}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  aiAvatar: { ...formData.aiAvatar, voiceTone: e.target.value }
                })
              }
              disabled={!isEditing}
              className="mystery-input"
            >
              <option value="warm">温暖</option>
              <option value="playful">俏皮</option>
              <option value="serious">严肃</option>
              <option value="gentle">温柔</option>
              <option value="energetic">活力</option>
            </select>
          </div>

          <div className="col-span-2">
            <label className="block text-sm font-medium mb-2 text-white/80">
              神秘等级: {formData.aiAvatar.mysteryLevel || 3}/5
            </label>
            <input
              type="range"
              min="1"
              max="5"
              value={formData.aiAvatar.mysteryLevel || 3}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  aiAvatar: { ...formData.aiAvatar, mysteryLevel: parseInt(e.target.value) }
                })
              }
              disabled={!isEditing}
              className="w-full"
            />
            <p className="text-xs text-white/50 mt-2">
              神秘等级越高，对方看到的信息越少
            </p>
          </div>
        </div>
      </motion.div>

      {/* 兴趣爱好 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="mystery-card"
      >
        <h3 className="text-xl font-bold mb-4 gradient-text">兴趣爱好</h3>

        <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
          {interestOptions.map((option) => (
            <motion.button
              key={option.value}
              whileHover={{ scale: isEditing ? 1.05 : 1 }}
              whileTap={{ scale: isEditing ? 0.95 : 1 }}
              onClick={() => isEditing && toggleInterest(option.value)}
              disabled={!isEditing}
              className={`p-4 rounded-xl border-2 transition-all ${
                formData.interests.includes(option.value)
                  ? 'bg-gradient-mystery border-purple-400'
                  : 'bg-white/5 border-white/20'
              } ${isEditing ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <div className="text-3xl mb-2">{option.icon}</div>
              <div className="text-sm">{option.label}</div>
            </motion.button>
          ))}
        </div>
      </motion.div>

      {/* 统计数据 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mystery-card"
      >
        <h3 className="text-xl font-bold mb-4 gradient-text">我的数据</h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'AI对话', value: user?.stats?.aiConversations || 0, icon: '💬' },
            { label: '匹配数', value: user?.stats?.matches || 0, icon: '💕' },
            { label: '参与活动', value: user?.stats?.activitiesAttended || 0, icon: '🎯' },
            { label: '游戏次数', value: user?.stats?.gamesPlayed || 0, icon: '🎮' }
          ].map((stat) => (
            <div key={stat.label} className="text-center p-4 bg-white/5 rounded-xl">
              <div className="text-3xl mb-2">{stat.icon}</div>
              <div className="text-2xl font-bold gradient-text mb-1">{stat.value}</div>
              <div className="text-sm text-white/60">{stat.label}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* 账户设置 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="mystery-card"
      >
        <h3 className="text-xl font-bold mb-4 gradient-text">账户信息</h3>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-2 border-b border-white/10">
            <span className="text-white/60">邮箱</span>
            <span>{user?.email}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-white/10">
            <span className="text-white/60">用户名</span>
            <span>{user?.username}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-white/10">
            <span className="text-white/60">注册时间</span>
            <span>{new Date(user?.createdAt).toLocaleDateString('zh-CN')}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-white/60">最后活跃</span>
            <span>{new Date(user?.lastActive).toLocaleDateString('zh-CN')}</span>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default Profile;
