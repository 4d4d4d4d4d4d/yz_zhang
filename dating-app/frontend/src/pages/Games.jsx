import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { gameAPI } from '../services/api';
import { useNavigate } from 'react-router-dom';

const Games = () => {
  const navigate = useNavigate();
  const [view, setView] = useState('explore'); // explore, my-games, create
  const [games, setGames] = useState([]);
  const [myGames, setMyGames] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedGameType, setSelectedGameType] = useState('');

  const gameTypes = [
    {
      type: 'truth-or-dare',
      name: '真心话大冒险',
      icon: '🎭',
      desc: '经典游戏，增进了解',
      color: 'from-pink-500 to-red-500'
    },
    {
      type: 'personality-test',
      name: '性格测试',
      icon: '🧠',
      desc: '了解你的性格类型',
      color: 'from-purple-500 to-indigo-500'
    },
    {
      type: 'would-you-rather',
      name: '宁愿选择',
      icon: '🤔',
      desc: '有趣的两难选择',
      color: 'from-blue-500 to-cyan-500'
    },
    {
      type: 'ice-breaker-cards',
      name: '破冰卡片',
      icon: '💭',
      desc: '开启话题的好方式',
      color: 'from-green-500 to-teal-500'
    }
  ];

  useEffect(() => {
    if (view === 'explore') {
      loadPublicGames();
    } else if (view === 'my-games') {
      loadMyGames();
    }
  }, [view]);

  const loadPublicGames = async () => {
    try {
      setLoading(true);
      const res = await gameAPI.getPublicGames({ status: 'waiting' });
      setGames(res.data.games);
    } catch (error) {
      console.error('Failed to load games:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadMyGames = async () => {
    try {
      setLoading(true);
      const res = await gameAPI.getMyGames();
      setMyGames(res.data.games);
    } catch (error) {
      console.error('Failed to load my games:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGame = async (gameType) => {
    try {
      const res = await gameAPI.createGame({
        type: gameType,
        settings: {
          isPrivate: false,
          allowSpectators: true
        }
      });

      alert('游戏创建成功！');
      navigate(`/game/${res.data.game._id}`);
    } catch (error) {
      alert('创建失败：' + (error.response?.data?.error || '未知错误'));
    }
  };

  const handleJoinGame = async (gameId) => {
    try {
      await gameAPI.joinGame(gameId);
      navigate(`/game/${gameId}`);
    } catch (error) {
      alert('加入失败：' + (error.response?.data?.error || '未知错误'));
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      {/* 顶部 */}
      <div className="text-center">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <h1 className="text-3xl font-bold gradient-text mb-2">互动游戏</h1>
          <p className="text-white/60">通过游戏增进了解，打破陌生感</p>
        </motion.div>
      </div>

      {/* 视图切换 */}
      <div className="flex space-x-4">
        <button
          onClick={() => setView('explore')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'explore' ? 'bg-gradient-mystery' : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          探索游戏
        </button>
        <button
          onClick={() => setView('my-games')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'my-games' ? 'bg-gradient-mystery' : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          我的游戏
        </button>
        <button
          onClick={() => setView('create')}
          className={`flex-1 py-3 rounded-xl font-semibold transition-all ${
            view === 'create' ? 'bg-gradient-mystery' : 'bg-white/10 hover:bg-white/20'
          }`}
        >
          创建游戏
        </button>
      </div>

      {/* 内容区域 */}
      {view === 'create' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-1 md:grid-cols-2 gap-6"
        >
          {gameTypes.map((game, index) => (
            <motion.div
              key={game.type}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.1 }}
              className="mystery-card hover-lift cursor-pointer"
              onClick={() => handleCreateGame(game.type)}
            >
              <div className={`w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br ${game.color} flex items-center justify-center text-5xl`}>
                {game.icon}
              </div>
              <h3 className="text-xl font-bold text-center mb-2">{game.name}</h3>
              <p className="text-white/60 text-center text-sm mb-4">{game.desc}</p>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="w-full mystery-button"
              >
                创建游戏
              </motion.button>
            </motion.div>
          ))}
        </motion.div>
      )}

      {view === 'explore' && (
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center min-h-[40vh]">
              <div className="loader" />
            </div>
          ) : games.length === 0 ? (
            <div className="mystery-card p-12 text-center">
              <div className="text-6xl mb-4">🎮</div>
              <h3 className="text-2xl font-bold mb-2">暂无公开游戏</h3>
              <p className="text-white/60 mb-6">创建一个游戏，邀请其他人加入吧！</p>
              <button
                onClick={() => setView('create')}
                className="mystery-button"
              >
                创建游戏
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {games.map((game) => {
                const gameType = gameTypes.find(g => g.type === game.type);
                return (
                  <motion.div
                    key={game._id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mystery-card hover-lift"
                  >
                    <div className="flex items-center space-x-4 mb-4">
                      <div className={`w-16 h-16 rounded-xl bg-gradient-to-br ${gameType?.color || 'from-purple-500 to-pink-500'} flex items-center justify-center text-3xl`}>
                        {gameType?.icon || '🎮'}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold">{game.name}</h3>
                        <p className="text-sm text-white/60">{gameType?.name}</p>
                      </div>
                    </div>

                    <div className="space-y-2 text-sm mb-4">
                      <div className="flex items-center justify-between">
                        <span className="text-white/60">参与者</span>
                        <span>{game.participants.length} 人</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-white/60">创建者</span>
                        <span>{game.createdBy?.username}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-white/60">状态</span>
                        <span className="badge">
                          {game.status === 'waiting' && '等待中'}
                          {game.status === 'in-progress' && '进行中'}
                          {game.status === 'completed' && '已完成'}
                        </span>
                      </div>
                    </div>

                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => handleJoinGame(game._id)}
                      className="w-full mystery-button text-sm"
                    >
                      加入游戏
                    </motion.button>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {view === 'my-games' && (
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center min-h-[40vh]">
              <div className="loader" />
            </div>
          ) : myGames.length === 0 ? (
            <div className="mystery-card p-12 text-center">
              <div className="text-6xl mb-4">🎲</div>
              <h3 className="text-2xl font-bold mb-2">还没有游戏记录</h3>
              <p className="text-white/60 mb-6">开始你的第一个游戏吧！</p>
              <button
                onClick={() => setView('create')}
                className="mystery-button"
              >
                创建游戏
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {myGames.map((game) => {
                const gameType = gameTypes.find(g => g.type === game.type);
                return (
                  <motion.div
                    key={game._id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mystery-card hover-lift cursor-pointer"
                    onClick={() => navigate(`/game/${game._id}`)}
                  >
                    <div className="flex items-center space-x-4 mb-4">
                      <div className={`w-16 h-16 rounded-xl bg-gradient-to-br ${gameType?.color || 'from-purple-500 to-pink-500'} flex items-center justify-center text-3xl`}>
                        {gameType?.icon || '🎮'}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold">{game.name}</h3>
                        <p className="text-sm text-white/60">{gameType?.name}</p>
                      </div>
                      <div className={`badge ${
                        game.status === 'completed' ? 'bg-green-500/20' :
                        game.status === 'in-progress' ? 'bg-blue-500/20' :
                        'bg-yellow-500/20'
                      }`}>
                        {game.status === 'waiting' && '等待中'}
                        {game.status === 'in-progress' && '进行中'}
                        {game.status === 'completed' && '已完成'}
                      </div>
                    </div>

                    <div className="space-y-2 text-sm">
                      <div className="flex items-center space-x-2 text-white/60">
                        <span>👥</span>
                        <span>{game.participants.length} 位参与者</span>
                      </div>
                      {game.stats?.totalQuestions > 0 && (
                        <div className="flex items-center space-x-2 text-white/60">
                          <span>❓</span>
                          <span>{game.stats.totalQuestions} 个问题</span>
                        </div>
                      )}
                      <div className="flex items-center space-x-2 text-white/60">
                        <span>📅</span>
                        <span>{new Date(game.createdAt).toLocaleDateString('zh-CN')}</span>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Games;
