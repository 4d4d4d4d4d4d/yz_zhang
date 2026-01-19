import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { interactiveGameAPI } from '../services/api';
import {
  ArrowLeftIcon,
  LockClosedIcon,
  UserGroupIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';

const CreateGameRoom = () => {
  const navigate = useNavigate();
  const [gameType, setGameType] = useState('draw_guess');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [maxParticipants, setMaxParticipants] = useState(8);
  const [isPrivate, setIsPrivate] = useState(false);
  const [password, setPassword] = useState('');
  const [scriptTheme, setScriptTheme] = useState('mystery_manor');
  const [scriptTemplates, setScriptTemplates] = useState({});
  const [loading, setLoading] = useState(false);

  const gameTypes = [
    { id: 'draw_guess', label: '你画我猜', emoji: '🎨', desc: '快速绘画，猜测词语' },
    { id: 'script_murder', label: '剧本杀', emoji: '🔍', desc: '沉浸式角色扮演推理' },
    { id: 'werewolf', label: '狼人杀', emoji: '🐺', desc: '策略推理，阵营对抗' },
    { id: 'truth_dare', label: '真心话大冒险', emoji: '💭', desc: '勇敢分享，接受挑战' },
    { id: 'word_chain', label: '成语接龙', emoji: '📖', desc: '文字游戏，考验词汇' },
    { id: 'riddle', label: '谜语竞猜', emoji: '🤔', desc: '智力挑战，猜测谜底' }
  ];

  useEffect(() => {
    loadScriptTemplates();
  }, []);

  const loadScriptTemplates = async () => {
    try {
      const response = await interactiveGameAPI.getScriptTemplates();
      setScriptTemplates(response.data.templates || {});
    } catch (error) {
      console.error('Load templates error:', error);
    }
  };

  const handleCreate = async () => {
    if (!title.trim()) {
      alert('请输入房间标题');
      return;
    }

    if (isPrivate && !password) {
      alert('私密房间需要设置密码');
      return;
    }

    try {
      setLoading(true);

      const gameData = {
        gameType,
        title,
        description,
        maxParticipants,
        settings: {
          isPrivate,
          password: isPrivate ? password : undefined
        }
      };

      if (gameType === 'script_murder') {
        gameData.scriptTheme = scriptTheme;
      }

      const response = await interactiveGameAPI.createGame(gameData);
      navigate(`/interactive-games/${response.data.game._id}`);
    } catch (error) {
      console.error('Create game error:', error);
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
          <h1 className="text-3xl font-bold text-white">创建游戏房间</h1>
        </div>

        <div className="space-y-6">
          {/* Game Type Selection */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mystery-card p-6"
          >
            <h2 className="text-xl font-bold text-white mb-4">选择游戏类型</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {gameTypes.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setGameType(type.id)}
                  className={`p-4 rounded-lg transition-all text-left ${
                    gameType === type.id
                      ? 'bg-purple-600 border-2 border-purple-400'
                      : 'bg-white/10 border-2 border-transparent hover:bg-white/20'
                  }`}
                >
                  <div className="text-3xl mb-2">{type.emoji}</div>
                  <div className="text-white font-semibold mb-1">{type.label}</div>
                  <div className="text-gray-400 text-xs">{type.desc}</div>
                </button>
              ))}
            </div>
          </motion.div>

          {/* Script Theme (for Script Murder) */}
          {gameType === 'script_murder' && Object.keys(scriptTemplates).length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mystery-card p-6"
            >
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <SparklesIcon className="w-6 h-6 text-yellow-400" />
                选择剧本
              </h2>
              <div className="space-y-3">
                {Object.entries(scriptTemplates).map(([key, template]) => (
                  <button
                    key={key}
                    onClick={() => setScriptTheme(key)}
                    className={`w-full p-4 rounded-lg transition-all text-left ${
                      scriptTheme === key
                        ? 'bg-purple-600 border-2 border-purple-400'
                        : 'bg-white/10 border-2 border-transparent hover:bg-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-white font-semibold">{template.title}</h3>
                      <span className={`px-2 py-1 rounded-full text-xs ${
                        template.difficulty === 'easy' ? 'bg-green-600' :
                        template.difficulty === 'medium' ? 'bg-yellow-600' :
                        'bg-red-600'
                      }`}>
                        {template.difficulty === 'easy' ? '简单' :
                         template.difficulty === 'medium' ? '中等' : '困难'}
                      </span>
                    </div>
                    <p className="text-gray-400 text-sm">{template.description}</p>
                    <p className="text-purple-300 text-xs mt-2">
                      {template.roles.length} 个角色
                    </p>
                  </button>
                ))}
              </div>
            </motion.div>
          )}

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
                房间标题 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="给你的房间起个名字"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div>
              <label className="text-gray-300 text-sm mb-2 block">房间描述</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="描述一下游戏规则或要求..."
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
          </motion.div>

          {/* Create Button */}
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            onClick={handleCreate}
            disabled={loading}
            className="w-full py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '创建中...' : '创建游戏房间'}
          </motion.button>
        </div>
      </div>
    </div>
  );
};

export default CreateGameRoom;
