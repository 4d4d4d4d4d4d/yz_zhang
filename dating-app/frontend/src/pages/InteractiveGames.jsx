import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { interactiveGameAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  PuzzlePieceIcon,
  PaintBrushIcon,
  UserGroupIcon,
  PlusCircleIcon,
  FireIcon
} from '@heroicons/react/24/outline';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';

const InteractiveGames = () => {
  const navigate = useNavigate();
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeGameType, setActiveGameType] = useState('all');

  const gameTypes = [
    { id: 'all', label: '全部', icon: PuzzlePieceIcon },
    { id: 'script_murder', label: '剧本杀', icon: '🔍' },
    { id: 'draw_guess', label: '你画我猜', icon: '🎨' },
    { id: 'werewolf', label: '狼人杀', icon: '🐺' },
    { id: 'truth_dare', label: '真心话大冒险', icon: '💭' }
  ];

  useEffect(() => {
    loadGames();
  }, [activeGameType]);

  const loadGames = async () => {
    try {
      setLoading(true);
      const params = activeGameType === 'all' ? {} : { gameType: activeGameType };
      const response = await interactiveGameAPI.getPublicGames(params);
      setGames(response.data.games || []);
    } catch (error) {
      console.error('Load games error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleJoinGame = async (gameId) => {
    try {
      await interactiveGameAPI.joinGame(gameId, {});
      navigate(`/interactive-games/${gameId}`);
    } catch (error) {
      console.error('Join game error:', error);
      alert(error.response?.data?.error || '加入游戏失败');
    }
  };

  const getGameTypeLabel = (type) => {
    const typeMap = {
      script_murder: '剧本杀',
      draw_guess: '你画我猜',
      werewolf: '狼人杀',
      mafia: '天黑请闭眼',
      truth_dare: '真心话大冒险',
      word_chain: '成语接龙',
      riddle: '谜语竞猜',
      karaoke: 'K歌房'
    };
    return typeMap[type] || type;
  };

  const getStatusColor = (status) => {
    const colors = {
      waiting: 'bg-yellow-600/30 text-yellow-300',
      started: 'bg-green-600/30 text-green-300',
      completed: 'bg-gray-600/30 text-gray-300'
    };
    return colors[status] || colors.waiting;
  };

  const getStatusLabel = (status) => {
    const labels = {
      waiting: '等待中',
      started: '进行中',
      completed: '已完成'
    };
    return labels[status] || status;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6 pb-24">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <PuzzlePieceIcon className="w-8 h-8 text-purple-400" />
            互动游戏
          </h1>
          <button
            onClick={() => navigate('/interactive-games/create')}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all flex items-center gap-2"
          >
            <PlusCircleIcon className="w-5 h-5" />
            创建游戏
          </button>
        </div>

        {/* Game Type Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          {gameTypes.map((type) => (
            <button
              key={type.id}
              onClick={() => setActiveGameType(type.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-all ${
                activeGameType === type.id
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              {typeof type.icon === 'string' ? (
                <span className="text-xl">{type.icon}</span>
              ) : (
                <type.icon className="w-5 h-5" />
              )}
              {type.label}
            </button>
          ))}
        </div>

        {/* Games Grid */}
        {loading ? (
          <Loading message="加载游戏列表..." />
        ) : games.length === 0 ? (
          <EmptyState
            icon={PuzzlePieceIcon}
            title="暂无游戏"
            description="创建第一个游戏房间，开始互动吧！"
            action={() => navigate('/interactive-games/create')}
            actionLabel="创建游戏"
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {games.map((game) => (
              <motion.div
                key={game._id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mystery-card p-6 cursor-pointer hover:shadow-2xl transition-all"
                onClick={() => handleJoinGame(game._id)}
              >
                {/* Game Type Badge */}
                <div className="flex items-center justify-between mb-4">
                  <span className="px-3 py-1 bg-purple-600/30 text-purple-300 text-sm rounded-full">
                    {getGameTypeLabel(game.gameType)}
                  </span>
                  <span className={`px-3 py-1 text-sm rounded-full ${getStatusColor(game.status)}`}>
                    {getStatusLabel(game.status)}
                  </span>
                </div>

                {/* Title */}
                <h3 className="text-xl font-bold text-white mb-2">{game.title}</h3>

                {/* Description */}
                {game.description && (
                  <p className="text-gray-400 text-sm mb-4 line-clamp-2">{game.description}</p>
                )}

                {/* Host */}
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center">
                    {game.host.profile?.aiAvatar?.emoji || '👤'}
                  </div>
                  <div>
                    <p className="text-gray-400 text-xs">房主</p>
                    <p className="text-white text-sm font-semibold">
                      {game.host.profile?.displayName || game.host.username}
                    </p>
                  </div>
                </div>

                {/* Participants */}
                <div className="flex items-center justify-between pt-4 border-t border-white/10">
                  <div className="flex items-center gap-2 text-gray-300">
                    <UserGroupIcon className="w-5 h-5" />
                    <span className="text-sm">
                      {game.participants.length}/{game.maxParticipants} 人
                    </span>
                  </div>

                  {game.status === 'waiting' && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleJoinGame(game._id);
                      }}
                      className="px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white text-sm rounded-lg hover:shadow-lg transition-all"
                    >
                      加入
                    </button>
                  )}

                  {game.status === 'started' && (
                    <span className="text-green-400 text-sm flex items-center gap-1">
                      <FireIcon className="w-4 h-4" />
                      进行中
                    </span>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Popular Games Section */}
        <div className="mt-12 mystery-card p-6">
          <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
            <FireIcon className="w-7 h-7 text-orange-400" />
            热门游戏玩法
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-white/5 rounded-lg">
              <h3 className="text-lg font-semibold text-purple-300 mb-2 flex items-center gap-2">
                <span className="text-2xl">🔍</span>
                剧本杀
              </h3>
              <p className="text-gray-400 text-sm">
                沉浸式角色扮演，推理解谜，找出真相
              </p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <h3 className="text-lg font-semibold text-pink-300 mb-2 flex items-center gap-2">
                <span className="text-2xl">🎨</span>
                你画我猜
              </h3>
              <p className="text-gray-400 text-sm">
                快速绘画，猜测词语，比拼默契
              </p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <h3 className="text-lg font-semibold text-blue-300 mb-2 flex items-center gap-2">
                <span className="text-2xl">🐺</span>
                狼人杀
              </h3>
              <p className="text-gray-400 text-sm">
                策略推理，阵营对抗，考验逻辑
              </p>
            </div>

            <div className="p-4 bg-white/5 rounded-lg">
              <h3 className="text-lg font-semibold text-yellow-300 mb-2 flex items-center gap-2">
                <span className="text-2xl">💭</span>
                真心话大冒险
              </h3>
              <p className="text-gray-400 text-sm">
                勇敢分享，接受挑战，快速破冰
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InteractiveGames;
