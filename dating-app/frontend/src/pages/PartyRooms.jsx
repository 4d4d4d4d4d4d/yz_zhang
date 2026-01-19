import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { partyRoomAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  MicrophoneIcon,
  VideoCameraIcon,
  MusicalNoteIcon,
  UserGroupIcon,
  PlusCircleIcon,
  FireIcon,
  LockClosedIcon
} from '@heroicons/react/24/outline';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';

const PartyRooms = () => {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeType, setActiveType] = useState('all');

  const roomTypes = [
    { id: 'all', label: '全部', icon: UserGroupIcon },
    { id: 'voice', label: '语音房', icon: MicrophoneIcon },
    { id: 'video', label: '视频房', icon: VideoCameraIcon },
    { id: 'music', label: '音乐房', icon: MusicalNoteIcon }
  ];

  const themes = {
    casual: { label: '闲聊', color: 'text-blue-400', emoji: '💬' },
    dating: { label: '交友', color: 'text-pink-400', emoji: '💕' },
    music: { label: '音乐', color: 'text-purple-400', emoji: '🎵' },
    gaming: { label: '游戏', color: 'text-green-400', emoji: '🎮' },
    study: { label: '学习', color: 'text-yellow-400', emoji: '📚' },
    night_chat: { label: '夜聊', color: 'text-indigo-400', emoji: '🌙' },
    emotion_sharing: { label: '情绪树洞', color: 'text-red-400', emoji: '💭' },
    soul_mate: { label: '灵魂伴侣', color: 'text-purple-300', emoji: '✨' }
  };

  useEffect(() => {
    loadRooms();
  }, [activeType]);

  const loadRooms = async () => {
    try {
      setLoading(true);
      const params = activeType === 'all' ? {} : { type: activeType };
      const response = await partyRoomAPI.getActiveRooms(params);
      setRooms(response.data.rooms || []);
    } catch (error) {
      console.error('Load rooms error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleJoinRoom = async (roomId) => {
    try {
      await partyRoomAPI.joinRoom(roomId, {});
      navigate(`/party-rooms/${roomId}`);
    } catch (error) {
      console.error('Join room error:', error);
      if (error.response?.status === 401) {
        const password = prompt('请输入房间密码：');
        if (password) {
          try {
            await partyRoomAPI.joinRoom(roomId, { password });
            navigate(`/party-rooms/${roomId}`);
          } catch (err) {
            alert('密码错误');
          }
        }
      } else {
        alert(error.response?.data?.error || '加入房间失败');
      }
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6 pb-24">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <MicrophoneIcon className="w-8 h-8 text-purple-400" />
            派对房间
          </h1>
          <button
            onClick={() => navigate('/party-rooms/create')}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center gap-2"
          >
            <PlusCircleIcon className="w-5 h-5" />
            创建房间
          </button>
        </div>

        {/* Room Type Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          {roomTypes.map((type) => {
            const Icon = type.icon;
            return (
              <button
                key={type.id}
                onClick={() => setActiveType(type.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-all ${
                  activeType === type.id
                    ? 'bg-purple-600 text-white'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                <Icon className="w-5 h-5" />
                {type.label}
              </button>
            );
          })}
        </div>

        {/* Rooms Grid */}
        {loading ? (
          <Loading message="加载房间列表..." />
        ) : rooms.length === 0 ? (
          <EmptyState
            icon={MicrophoneIcon}
            title="暂无房间"
            description="创建第一个派对房间，开始聊天吧！"
            action={() => navigate('/party-rooms/create')}
            actionLabel="创建房间"
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {rooms.map((room) => {
              const themeInfo = themes[room.theme] || themes.casual;
              const occupiedSeats = room.seats?.filter(s => s.occupiedBy).length || 0;

              return (
                <motion.div
                  key={room._id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mystery-card p-6 cursor-pointer hover:shadow-2xl transition-all"
                  onClick={() => handleJoinRoom(room._id)}
                >
                  {/* Header */}
                  <div className="flex items-center justify-between mb-4">
                    <span className={`px-3 py-1 bg-white/10 rounded-full text-sm flex items-center gap-1 ${themeInfo.color}`}>
                      <span>{themeInfo.emoji}</span>
                      {themeInfo.label}
                    </span>
                    {room.settings?.isPrivate && (
                      <LockClosedIcon className="w-5 h-5 text-gray-400" />
                    )}
                  </div>

                  {/* Title */}
                  <h3 className="text-xl font-bold text-white mb-2 line-clamp-1">{room.name}</h3>

                  {/* Description */}
                  {room.description && (
                    <p className="text-gray-400 text-sm mb-4 line-clamp-2">{room.description}</p>
                  )}

                  {/* Silent Mode Badge */}
                  {room.silentMode?.enabled && (
                    <div className="mb-4 px-3 py-2 bg-indigo-600/30 border border-indigo-500/50 rounded-lg">
                      <p className="text-indigo-300 text-sm flex items-center gap-2">
                        <span>🤫</span>
                        无声连麦模式
                      </p>
                    </div>
                  )}

                  {/* Host */}
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                      {room.host.profile?.aiAvatar?.emoji || '👤'}
                    </div>
                    <div>
                      <p className="text-gray-400 text-xs">房主</p>
                      <p className="text-white text-sm font-semibold">
                        {room.host.profile?.displayName || room.host.username}
                      </p>
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="flex items-center justify-between pt-4 border-t border-white/10">
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-1 text-gray-300">
                        <UserGroupIcon className="w-5 h-5" />
                        <span className="text-sm">{room.participants.length}</span>
                      </div>
                      {room.type === 'voice' && (
                        <div className="flex items-center gap-1 text-gray-300">
                          <MicrophoneIcon className="w-5 h-5" />
                          <span className="text-sm">{occupiedSeats}/{room.seats?.length || 0}</span>
                        </div>
                      )}
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleJoinRoom(room._id);
                      }}
                      className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm rounded-lg hover:shadow-lg transition-all"
                    >
                      加入
                    </button>
                  </div>

                  {/* Participants Preview */}
                  {room.participants.length > 0 && (
                    <div className="flex -space-x-2 mt-4">
                      {room.participants.slice(0, 5).map((p, idx) => (
                        <div
                          key={idx}
                          className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center border-2 border-gray-900"
                          title={p.user.profile?.displayName || p.user.username}
                        >
                          <span className="text-sm">
                            {p.user.profile?.aiAvatar?.emoji || '👤'}
                          </span>
                        </div>
                      ))}
                      {room.participants.length > 5 && (
                        <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center border-2 border-gray-900 text-white text-xs">
                          +{room.participants.length - 5}
                        </div>
                      )}
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        )}

        {/* Features Section */}
        <div className="mt-12 mystery-card p-6">
          <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
            <FireIcon className="w-7 h-7 text-orange-400" />
            房间特色
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 bg-white/5 rounded-lg">
              <div className="text-3xl mb-2">🎤</div>
              <h3 className="text-lg font-semibold text-white mb-1">语音连麦</h3>
              <p className="text-gray-400 text-sm">实时语音交流，结识新朋友</p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <div className="text-3xl mb-2">🤫</div>
              <h3 className="text-lg font-semibold text-white mb-1">无声连麦</h3>
              <p className="text-gray-400 text-sm">安静陪伴，治愈孤独</p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <div className="text-3xl mb-2">🎵</div>
              <h3 className="text-lg font-semibold text-white mb-1">音乐房</h3>
              <p className="text-gray-400 text-sm">一起听歌，分享旋律</p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <div className="text-3xl mb-2">💭</div>
              <h3 className="text-lg font-semibold text-white mb-1">情绪树洞</h3>
              <p className="text-gray-400 text-sm">倾诉心事，获得共鸣</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PartyRooms;
