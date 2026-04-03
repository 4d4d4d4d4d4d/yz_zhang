import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { partyRoomAPI } from '../services/api';
import socketService from '../services/socket';
import useAuthStore from '../store/authStore';
import {
  UserGroupIcon,
  ChatBubbleLeftIcon,
  MicrophoneIcon,
  SpeakerWaveIcon,
  SpeakerXMarkIcon,
  ArrowLeftIcon,
  HeartIcon,
  MusicalNoteIcon,
  VideoCameraIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import Loading from '../components/Loading';

const PartyRoomDetail = () => {
  const { roomId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [room, setRoom] = useState(null);
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [messageInput, setMessageInput] = useState('');
  const [myMuted, setMyMuted] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadRoomDetails();

    // Join socket room
    socketService.socket?.emit('join_party_room', { roomId });

    // Listen for room updates
    socketService.socket?.on('party_room_updated', (updatedRoom) => {
      setRoom(updatedRoom);
    });

    socketService.socket?.on('room_message', (message) => {
      setMessages(prev => [...prev, message]);
      scrollToBottom();
    });

    socketService.socket?.on('user_joined_room', (data) => {
      setMessages(prev => [...prev, {
        type: 'system',
        content: `${data.user.profile?.displayName || data.user.username} 加入了房间`,
        timestamp: new Date()
      }]);
    });

    socketService.socket?.on('user_left_room', (data) => {
      setMessages(prev => [...prev, {
        type: 'system',
        content: `${data.user.profile?.displayName || data.user.username} 离开了房间`,
        timestamp: new Date()
      }]);
    });

    socketService.socket?.on('seat_taken', (data) => {
      setMessages(prev => [...prev, {
        type: 'system',
        content: `${data.user.profile?.displayName || data.user.username} 上了${data.seatNumber}号麦`,
        timestamp: new Date()
      }]);
    });

    return () => {
      socketService.socket?.emit('leave_party_room', { roomId });
      socketService.socket?.off('party_room_updated');
      socketService.socket?.off('room_message');
      socketService.socket?.off('user_joined_room');
      socketService.socket?.off('user_left_room');
      socketService.socket?.off('seat_taken');
    };
  }, [roomId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadRoomDetails = async () => {
    try {
      setLoading(true);
      const response = await partyRoomAPI.getRoomDetails(roomId);
      setRoom(response.data);
    } catch (error) {
      console.error('Load room error:', error);
      alert('加载房间失败');
      navigate('/party-rooms');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim()) return;

    try {
      await partyRoomAPI.sendMessage(roomId, { message: messageInput });
      setMessageInput('');
    } catch (error) {
      console.error('Send message error:', error);
    }
  };

  const handleTakeSeat = async (seatNumber) => {
    try {
      await partyRoomAPI.takeSeat(roomId, { seatNumber });
    } catch (error) {
      alert(error.response?.data?.error || '上麦失败');
    }
  };

  const handleLeaveSeat = async () => {
    try {
      await partyRoomAPI.leaveSeat(roomId);
    } catch (error) {
      alert(error.response?.data?.error || '下麦失败');
    }
  };

  const handleLeaveRoom = async () => {
    try {
      await partyRoomAPI.leaveRoom(roomId);
      navigate('/party-rooms');
    } catch (error) {
      console.error('Leave room error:', error);
    }
  };

  const handleEndRoom = async () => {
    if (!confirm('确定要结束房间吗？')) return;

    try {
      await partyRoomAPI.endRoom(roomId);
      navigate('/party-rooms');
    } catch (error) {
      alert(error.response?.data?.error || '结束房间失败');
    }
  };

  const isHost = room?.host?._id === user._id;
  const mySeat = room?.seats?.find(seat => seat.occupiedBy?._id === user._id);

  if (loading) return <Loading />;
  if (!room) return <div className="text-white text-center mt-20">房间不存在</div>;

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mystery-card p-6 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <button
                onClick={handleLeaveRoom}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <ArrowLeftIcon className="w-6 h-6" />
              </button>
              <div>
                <div className="flex items-center gap-2 mb-2">
                  {room.type === 'voice' && <MicrophoneIcon className="w-6 h-6 text-purple-400" />}
                  {room.type === 'video' && <VideoCameraIcon className="w-6 h-6 text-pink-400" />}
                  {room.type === 'music' && <MusicalNoteIcon className="w-6 h-6 text-blue-400" />}
                  <h1 className="text-3xl font-bold text-white">{room.title}</h1>
                </div>
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span className="flex items-center gap-1">
                    <UserGroupIcon className="w-4 h-4" />
                    {room.participants.length}/{room.maxParticipants}
                  </span>
                  <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded-full text-xs">
                    {room.theme === 'casual' ? '休闲' :
                     room.theme === 'dating' ? '交友' :
                     room.theme === 'music' ? '音乐' :
                     room.theme === 'gaming' ? '游戏' :
                     room.theme === 'study' ? '学习' :
                     room.theme === 'night_chat' ? '夜聊' :
                     room.theme === 'emotion_sharing' ? '情感' : '灵魂匹配'}
                  </span>
                  {room.silentMode.enabled && (
                    <span className="px-2 py-1 bg-blue-500/20 text-blue-300 rounded-full text-xs flex items-center gap-1">
                      <SparklesIcon className="w-3 h-3" />
                      静默连麦
                    </span>
                  )}
                </div>
              </div>
            </div>

            {isHost && (
              <button
                onClick={handleEndRoom}
                className="px-4 py-2 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30 transition-all"
              >
                结束房间
              </button>
            )}
          </div>

          {room.description && (
            <p className="text-gray-300 mb-4">{room.description}</p>
          )}

          {room.silentMode.enabled && (
            <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
              <div className="flex items-center gap-2 text-blue-300 font-semibold mb-1">
                <SparklesIcon className="w-5 h-5" />
                静默连麦模式
              </div>
              <p className="text-gray-400 text-sm">
                {room.silentMode.description || '在这里，我们用心感受彼此的存在，无需言语也能传递温暖'}
              </p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Seats Area */}
          <div className="lg:col-span-2">
            <div className="mystery-card p-6">
              <h2 className="text-xl font-bold text-white mb-4">麦位</h2>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                {room.seats.map((seat) => (
                  <SeatCard
                    key={seat.number}
                    seat={seat}
                    onTakeSeat={handleTakeSeat}
                    isMyAccount={user._id}
                    isHost={isHost}
                    roomType={room.type}
                    mySeat={mySeat}
                  />
                ))}
              </div>

              {mySeat && (
                <div className="flex justify-center">
                  <button
                    onClick={handleLeaveSeat}
                    className="px-6 py-3 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30 transition-all"
                  >
                    下麦
                  </button>
                </div>
              )}
            </div>

            {/* Audience */}
            <div className="mystery-card p-6 mt-4">
              <h3 className="text-xl font-bold text-white mb-4">观众席</h3>
              <div className="flex flex-wrap gap-2">
                {room.participants
                  .filter(p => !room.seats.some(s => s.occupiedBy?._id === p._id))
                  .map((participant) => (
                    <div
                      key={participant._id}
                      className="flex items-center gap-2 px-3 py-2 bg-white/10 rounded-lg"
                    >
                      <div className="w-8 h-8 rounded-full bg-gradient-mystery flex items-center justify-center text-white text-sm font-bold">
                        {participant.profile?.displayName?.[0] || participant.username[0]}
                      </div>
                      <span className="text-white text-sm">
                        {participant.profile?.displayName || participant.username}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          {/* Chat Sidebar */}
          <div className="mystery-card p-4 h-[600px] flex flex-col">
            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <ChatBubbleLeftIcon className="w-5 h-5" />
              聊天
            </h3>

            <div className="flex-1 overflow-y-auto mb-4 space-y-2">
              {messages.map((msg, idx) => (
                <div key={idx}>
                  {msg.type === 'system' ? (
                    <div className="text-center text-gray-400 text-sm py-1">
                      {msg.content}
                    </div>
                  ) : (
                    <div className="p-2 bg-white/5 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        {msg.sender && (
                          <>
                            <div className="w-6 h-6 rounded-full bg-gradient-mystery flex items-center justify-center text-white text-xs font-bold">
                              {msg.sender.profile?.displayName?.[0] || msg.sender.username[0]}
                            </div>
                            <span className="text-purple-300 text-sm font-semibold">
                              {msg.sender.profile?.displayName || msg.sender.username}
                            </span>
                          </>
                        )}
                      </div>
                      <div className="text-white text-sm pl-8">{msg.message}</div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder={room.silentMode.enabled ? '用心感受...' : '输入消息...'}
                className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <button
                onClick={handleSendMessage}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Seat Card Component
const SeatCard = ({ seat, onTakeSeat, isMyAccount, isHost, roomType, mySeat }) => {
  const isEmpty = !seat.occupiedBy;
  const isLocked = seat.isLocked;
  const isMySeat = seat.occupiedBy?._id === isMyAccount;

  const handleClick = () => {
    if (isEmpty && !isLocked && !mySeat) {
      onTakeSeat(seat.number);
    }
  };

  return (
    <motion.div
      whileHover={isEmpty && !isLocked && !mySeat ? { scale: 1.05 } : {}}
      whileTap={isEmpty && !isLocked && !mySeat ? { scale: 0.95 } : {}}
      onClick={handleClick}
      className={`relative p-4 rounded-xl border-2 transition-all ${
        isEmpty
          ? isLocked
            ? 'bg-gray-500/10 border-gray-500/30 cursor-not-allowed'
            : mySeat
              ? 'bg-white/5 border-white/20 cursor-not-allowed'
              : 'bg-white/5 border-purple-500/50 cursor-pointer hover:border-purple-500'
          : isMySeat
            ? 'bg-purple-500/20 border-purple-500'
            : 'bg-white/10 border-white/20'
      }`}
    >
      {/* Seat Number */}
      <div className="absolute top-2 left-2 w-6 h-6 bg-white/20 rounded-full flex items-center justify-center text-white text-xs font-bold">
        {seat.number}
      </div>

      {/* Content */}
      <div className="flex flex-col items-center justify-center h-32">
        {isEmpty ? (
          <>
            {isLocked ? (
              <div className="text-gray-500 text-4xl mb-2">🔒</div>
            ) : (
              <div className="text-gray-400 text-4xl mb-2">
                {roomType === 'voice' ? '🎤' :
                 roomType === 'video' ? '📹' :
                 roomType === 'music' ? '🎵' : '💬'}
              </div>
            )}
            <span className="text-gray-400 text-sm">
              {isLocked ? '已锁定' : mySeat ? '已上麦' : '点击上麦'}
            </span>
          </>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-gradient-mystery flex items-center justify-center text-white text-2xl font-bold mb-2">
              {seat.occupiedBy.profile?.displayName?.[0] || seat.occupiedBy.username[0]}
            </div>
            <div className="text-white font-semibold text-center mb-1">
              {seat.occupiedBy.profile?.displayName || seat.occupiedBy.username}
            </div>
            {seat.isMuted ? (
              <SpeakerXMarkIcon className="w-5 h-5 text-red-400" />
            ) : (
              <SpeakerWaveIcon className="w-5 h-5 text-green-400 animate-pulse" />
            )}
          </>
        )}
      </div>

      {/* My Seat Indicator */}
      {isMySeat && (
        <div className="absolute top-2 right-2">
          <div className="w-6 h-6 bg-purple-500 rounded-full flex items-center justify-center">
            <span className="text-white text-xs">我</span>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default PartyRoomDetail;
