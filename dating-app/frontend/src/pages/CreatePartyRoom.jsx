import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { partyRoomAPI } from '../services/api';
import {
  ArrowLeftIcon,
  MicrophoneIcon,
  VideoCameraIcon,
  MusicalNoteIcon,
  ChatBubbleLeftRightIcon,
  LockClosedIcon,
  UserGroupIcon
} from '@heroicons/react/24/outline';

const CreatePartyRoom = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState('voice');
  const [theme, setTheme] = useState('casual');
  const [maxParticipants, setMaxParticipants] = useState(8);
  const [isPrivate, setIsPrivate] = useState(false);
  const [password, setPassword] = useState('');
  const [silentMode, setSilentMode] = useState(false);
  const [loading, setLoading] = useState(false);

  const roomTypes = [
    { id: 'voice', label: '语音房', icon: MicrophoneIcon, desc: '语音连麦交流' },
    { id: 'video', label: '视频房', icon: VideoCameraIcon, desc: '视频面对面' },
    { id: 'music', label: '音乐房', icon: MusicalNoteIcon, desc: '一起听歌' },
    { id: 'chat', label: '聊天房', icon: ChatBubbleLeftRightIcon, desc: '文字交流' }
  ];

  const themes = [
    { id: 'casual', label: '闲聊', emoji: '💬', color: 'blue' },
    { id: 'dating', label: '交友', emoji: '💕', color: 'pink' },
    { id: 'music', label: '音乐', emoji: '🎵', color: 'purple' },
    { id: 'gaming', label: '游戏', emoji: '🎮', color: 'green' },
    { id: 'study', label: '学习', emoji: '📚', color: 'yellow' },
    { id: 'night_chat', label: '夜聊', emoji: '🌙', color: 'indigo' },
    { id: 'emotion_sharing', label: '情绪树洞', emoji: '💭', color: 'red' },
    { id: 'soul_mate', label: '灵魂伴侣', emoji: '✨', color: 'purple' }
  ];

  const handleCreate = async () => {
    if (!name.trim()) {
      alert('请输入房间名称');
      return;
    }

    if (isPrivate && !password) {
      alert('私密房间需要设置密码');
      return;
    }

    try {
      setLoading(true);

      const roomData = {
        name,
        description,
        type,
        theme,
        maxParticipants,
        settings: {
          isPrivate,
          password: isPrivate ? password : undefined,
          allowGuests: true,
          muteNewcomers: false
        },
        silentMode: {
          enabled: silentMode,
          description: silentMode ? '无声连麦，安静陪伴' : undefined
        }
      };

      const response = await partyRoomAPI.createRoom(roomData);
      navigate(`/party-rooms/${response.data.room._id}`);
    } catch (error) {
      console.error('Create room error:', error);
      alert(error.response?.data?.error || '创建失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6 pb-24">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="text-gray-300 hover:text-white transition-colors"
          >
            <ArrowLeftIcon className="w-6 h-6" />
          </button>
          <h1 className="text-3xl font-bold text-white">创建派对房间</h1>
        </div>

        <div className="space-y-6">
          {/* Room Type Selection */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mystery-card p-6"
          >
            <h2 className="text-xl font-bold text-white mb-4">房间类型</h2>
            <div className="grid grid-cols-2 gap-3">
              {roomTypes.map((roomType) => {
                const Icon = roomType.icon;
                return (
                  <button
                    key={roomType.id}
                    onClick={() => setType(roomType.id)}
                    className={`p-4 rounded-lg transition-all text-left ${
                      type === roomType.id
                        ? 'bg-purple-600 border-2 border-purple-400'
                        : 'bg-white/10 border-2 border-transparent hover:bg-white/20'
                    }`}
                  >
                    <Icon className="w-8 h-8 mb-2 text-white" />
                    <div className="text-white font-semibold mb-1">{roomType.label}</div>
                    <div className="text-gray-400 text-xs">{roomType.desc}</div>
                  </button>
                );
              })}
            </div>
          </motion.div>

          {/* Theme Selection */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="mystery-card p-6"
          >
            <h2 className="text-xl font-bold text-white mb-4">房间主题</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {themes.map((themeOption) => (
                <button
                  key={themeOption.id}
                  onClick={() => setTheme(themeOption.id)}
                  className={`p-3 rounded-lg transition-all text-center ${
                    theme === themeOption.id
                      ? 'bg-purple-600 scale-105'
                      : 'bg-white/10 hover:bg-white/20'
                  }`}
                >
                  <div className="text-3xl mb-1">{themeOption.emoji}</div>
                  <div className="text-white text-sm font-semibold">{themeOption.label}</div>
                </button>
              ))}
            </div>
          </motion.div>

          {/* Room Settings */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mystery-card p-6 space-y-4"
          >
            <h2 className="text-xl font-bold text-white mb-4">房间设置</h2>

            <div>
              <label className="text-gray-300 text-sm mb-2 block">
                房间名称 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="给你的房间起个名字"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="text-gray-300 text-sm mb-2 block">房间简介</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="介绍一下这个房间..."
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                rows={3}
              />
            </div>

            <div>
              <label className="text-gray-300 text-sm mb-2 block flex items-center gap-2">
                <UserGroupIcon className="w-5 h-5" />
                最大人数: {maxParticipants}
              </label>
              <input
                type="range"
                min="2"
                max="20"
                value={maxParticipants}
                onChange={(e) => setMaxParticipants(parseInt(e.target.value))}
                className="w-full"
              />
            </div>

            <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg">
              <div className="flex items-center gap-3">
                <LockClosedIcon className="w-5 h-5 text-purple-400" />
                <div>
                  <h3 className="text-white font-semibold">私密房间</h3>
                  <p className="text-gray-400 text-sm">需要密码才能加入</p>
                </div>
              </div>
              <button
                onClick={() => setIsPrivate(!isPrivate)}
                className={`relative w-14 h-7 rounded-full transition-colors ${
                  isPrivate ? 'bg-purple-600' : 'bg-gray-600'
                }`}
              >
                <motion.div
                  animate={{ x: isPrivate ? 28 : 2 }}
                  className="absolute top-1 w-5 h-5 bg-white rounded-full"
                />
              </button>
            </div>

            {isPrivate && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
              >
                <label className="text-gray-300 text-sm mb-2 block">房间密码</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="设置房间密码"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </motion.div>
            )}

            {/* Silent Mode Toggle */}
            <div className="flex items-center justify-between p-4 bg-indigo-900/30 rounded-lg border border-indigo-500/30">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🤫</span>
                <div>
                  <h3 className="text-white font-semibold">无声连麦模式</h3>
                  <p className="text-gray-400 text-sm">静静陪伴，治愈孤独</p>
                </div>
              </div>
              <button
                onClick={() => setSilentMode(!silentMode)}
                className={`relative w-14 h-7 rounded-full transition-colors ${
                  silentMode ? 'bg-indigo-600' : 'bg-gray-600'
                }`}
              >
                <motion.div
                  animate={{ x: silentMode ? 28 : 2 }}
                  className="absolute top-1 w-5 h-5 bg-white rounded-full"
                />
              </button>
            </div>
          </motion.div>

          {/* Create Button */}
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15 }}
            onClick={handleCreate}
            disabled={loading}
            className="w-full py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '创建中...' : '创建派对房间'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CreatePartyRoom;
