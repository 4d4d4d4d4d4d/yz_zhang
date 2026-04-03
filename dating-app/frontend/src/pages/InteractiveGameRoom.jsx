import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { interactiveGameAPI } from '../services/api';
import socketService from '../services/socket';
import useAuthStore from '../store/authStore';
import {
  UserGroupIcon,
  ChatBubbleLeftIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  SparklesIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import Loading from '../components/Loading';

const InteractiveGameRoom = () => {
  const { gameId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [game, setGame] = useState(null);
  const [loading, setLoading] = useState(true);
  const [chatMessages, setChatMessages] = useState([]);
  const [messageInput, setMessageInput] = useState('');
  const canvasRef = useRef(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [guessInput, setGuessInput] = useState('');
  const [myRole, setMyRole] = useState(null);

  useEffect(() => {
    loadGameDetails();

    // Join socket room
    socketService.socket?.emit('join_game_room', { gameId });

    // Listen for game updates
    socketService.socket?.on('game_updated', (updatedGame) => {
      setGame(updatedGame);
    });

    socketService.socket?.on('game_chat', (message) => {
      setChatMessages(prev => [...prev, message]);
    });

    socketService.socket?.on('new_drawing', (drawingData) => {
      if (game?.gameType === 'draw_guess' && canvasRef.current) {
        redrawCanvas(drawingData);
      }
    });

    return () => {
      socketService.socket?.emit('leave_game_room', { gameId });
      socketService.socket?.off('game_updated');
      socketService.socket?.off('game_chat');
      socketService.socket?.off('new_drawing');
    };
  }, [gameId]);

  const loadGameDetails = async () => {
    try {
      setLoading(true);
      const response = await interactiveGameAPI.getGameDetails(gameId);
      setGame(response.data);

      // Find my role if it's a script murder or werewolf game
      if (response.data.gameType === 'script_murder' && response.data.scriptData) {
        const role = response.data.scriptData.roles.find(r => r.assignedTo?._id === user._id);
        setMyRole(role);
      }
    } catch (error) {
      console.error('Load game error:', error);
      alert('加载游戏失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStartGame = async () => {
    try {
      await interactiveGameAPI.startGame(gameId);
    } catch (error) {
      alert(error.response?.data?.error || '开始游戏失败');
    }
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim()) return;

    try {
      await interactiveGameAPI.sendChat(gameId, { message: messageInput });
      setMessageInput('');
    } catch (error) {
      console.error('Send message error:', error);
    }
  };

  // Drawing functions for Draw & Guess
  const startDrawing = (e) => {
    if (game?.gameType !== 'draw_guess' || !isMyTurnToDraw()) return;
    setIsDrawing(true);
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    ctx.beginPath();
    ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
  };

  const draw = (e) => {
    if (!isDrawing) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.stroke();

    // Emit drawing data to other players
    socketService.socket?.emit('drawing', {
      gameId,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    });
  };

  const stopDrawing = () => {
    setIsDrawing(false);
  };

  const redrawCanvas = (drawingData) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.lineTo(drawingData.x, drawingData.y);
    ctx.stroke();
  };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  const handleSubmitGuess = async () => {
    if (!guessInput.trim()) return;

    try {
      await interactiveGameAPI.submitGuess(gameId, { guess: guessInput });
      setGuessInput('');
    } catch (error) {
      alert(error.response?.data?.error || '提交答案失败');
    }
  };

  const isMyTurnToDraw = () => {
    if (!game || game.gameType !== 'draw_guess') return false;
    const currentRound = game.drawGuessData?.currentRound;
    return currentRound?.drawer?._id === user._id;
  };

  if (loading) return <Loading />;
  if (!game) return <div className="text-white text-center mt-20">游戏不存在</div>;

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mystery-card p-6 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2">{game.title}</h1>
              <div className="flex items-center gap-4 text-sm text-gray-400">
                <span className="flex items-center gap-1">
                  <UserGroupIcon className="w-4 h-4" />
                  {game.participants.length}/{game.maxParticipants}
                </span>
                <span className={`px-3 py-1 rounded-full ${
                  game.status === 'waiting' ? 'bg-yellow-500/20 text-yellow-300' :
                  game.status === 'active' ? 'bg-green-500/20 text-green-300' :
                  'bg-gray-500/20 text-gray-300'
                }`}>
                  {game.status === 'waiting' ? '等待中' :
                   game.status === 'active' ? '进行中' : '已结束'}
                </span>
              </div>
            </div>

            {game.host._id === user._id && game.status === 'waiting' && (
              <button
                onClick={handleStartGame}
                disabled={game.participants.length < 2}
                className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all disabled:opacity-50"
              >
                开始游戏
              </button>
            )}
          </div>

          {/* Participants */}
          <div className="flex flex-wrap gap-2">
            {game.participants.map((participant, idx) => (
              <div
                key={participant._id}
                className="flex items-center gap-2 px-3 py-2 bg-white/10 rounded-lg"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-mystery flex items-center justify-center text-white font-bold">
                  {participant.profile?.displayName?.[0] || participant.username[0]}
                </div>
                <span className="text-white text-sm">
                  {participant.profile?.displayName || participant.username}
                  {participant._id === game.host._id && ' 👑'}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Game Area */}
          <div className="lg:col-span-2">
            {game.gameType === 'draw_guess' && game.status === 'active' && (
              <DrawGuessGame
                game={game}
                canvasRef={canvasRef}
                startDrawing={startDrawing}
                draw={draw}
                stopDrawing={stopDrawing}
                clearCanvas={clearCanvas}
                isMyTurn={isMyTurnToDraw()}
                guessInput={guessInput}
                setGuessInput={setGuessInput}
                handleSubmitGuess={handleSubmitGuess}
                user={user}
              />
            )}

            {game.gameType === 'script_murder' && game.status === 'active' && (
              <ScriptMurderGame
                game={game}
                myRole={myRole}
                user={user}
              />
            )}

            {game.gameType === 'werewolf' && game.status === 'active' && (
              <WerewolfGame
                game={game}
                user={user}
              />
            )}

            {game.status === 'waiting' && (
              <div className="mystery-card p-12 text-center">
                <ClockIcon className="w-16 h-16 text-purple-400 mx-auto mb-4" />
                <h3 className="text-2xl font-bold text-white mb-2">等待房主开始游戏</h3>
                <p className="text-gray-400">至少需要2名玩家才能开始</p>
              </div>
            )}
          </div>

          {/* Chat Sidebar */}
          <div className="mystery-card p-4 h-[600px] flex flex-col">
            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <ChatBubbleLeftIcon className="w-5 h-5" />
              聊天室
            </h3>

            <div className="flex-1 overflow-y-auto mb-4 space-y-2">
              {chatMessages.map((msg, idx) => (
                <div key={idx} className="p-2 bg-white/5 rounded-lg">
                  <div className="text-purple-300 text-sm font-semibold">
                    {msg.sender?.profile?.displayName || msg.sender?.username}
                  </div>
                  <div className="text-white text-sm">{msg.message}</div>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder="输入消息..."
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

// Draw & Guess Game Component
const DrawGuessGame = ({
  game,
  canvasRef,
  startDrawing,
  draw,
  stopDrawing,
  clearCanvas,
  isMyTurn,
  guessInput,
  setGuessInput,
  handleSubmitGuess,
  user
}) => {
  const currentRound = game.drawGuessData?.currentRound;

  return (
    <div className="mystery-card p-6">
      <div className="mb-4">
        <h2 className="text-2xl font-bold text-white mb-2">你画我猜</h2>
        <div className="flex items-center justify-between">
          <div className="text-gray-400">
            回合 {currentRound?.roundNumber || 0} / {game.drawGuessData?.rounds?.length || 0}
          </div>
          {isMyTurn && (
            <div className="text-purple-300 font-semibold">
              你的词: {currentRound?.word}
            </div>
          )}
          {!isMyTurn && (
            <div className="text-gray-400">
              {currentRound?.drawer?.profile?.displayName || currentRound?.drawer?.username} 正在画
            </div>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div className="relative mb-4">
        <canvas
          ref={canvasRef}
          width={800}
          height={600}
          className="w-full bg-white rounded-lg cursor-crosshair"
          onMouseDown={startDrawing}
          onMouseMove={draw}
          onMouseUp={stopDrawing}
          onMouseLeave={stopDrawing}
        />
        {isMyTurn && (
          <button
            onClick={clearCanvas}
            className="absolute top-4 right-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
          >
            清空
          </button>
        )}
      </div>

      {/* Guess Input */}
      {!isMyTurn && (
        <div className="flex gap-2">
          <input
            type="text"
            value={guessInput}
            onChange={(e) => setGuessInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSubmitGuess()}
            placeholder="输入你的猜测..."
            className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <button
            onClick={handleSubmitGuess}
            className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all"
          >
            提交
          </button>
        </div>
      )}

      {/* Guesses */}
      <div className="mt-4 space-y-2">
        <h3 className="text-white font-semibold">猜测记录:</h3>
        {currentRound?.guesses?.map((guess, idx) => (
          <div
            key={idx}
            className={`p-2 rounded-lg ${
              guess.correct ? 'bg-green-500/20 text-green-300' : 'bg-white/5 text-gray-300'
            }`}
          >
            <span className="font-semibold">
              {guess.player?.profile?.displayName || guess.player?.username}:
            </span>{' '}
            {guess.guess}
            {guess.correct && ' ✓'}
          </div>
        ))}
      </div>
    </div>
  );
};

// Script Murder Game Component
const ScriptMurderGame = ({ game, myRole, user }) => {
  return (
    <div className="mystery-card p-6">
      <h2 className="text-2xl font-bold text-white mb-4">剧本杀: {game.scriptData?.theme}</h2>

      {myRole && (
        <div className="mb-6 p-4 bg-purple-500/20 border border-purple-500/50 rounded-lg">
          <h3 className="text-xl font-bold text-purple-300 mb-2">你的角色: {myRole.name}</h3>
          <p className="text-gray-300 mb-4">{myRole.description}</p>

          {myRole.background && (
            <div className="mb-4">
              <h4 className="text-white font-semibold mb-2">背景故事:</h4>
              <p className="text-gray-300">{myRole.background}</p>
            </div>
          )}

          {myRole.objective && (
            <div className="mb-4">
              <h4 className="text-white font-semibold mb-2">任务目标:</h4>
              <p className="text-gray-300">{myRole.objective}</p>
            </div>
          )}
        </div>
      )}

      <div className="space-y-4">
        <div>
          <h3 className="text-xl font-bold text-white mb-2">剧本介绍</h3>
          <p className="text-gray-300">{game.scriptData?.description}</p>
        </div>

        <div>
          <h3 className="text-xl font-bold text-white mb-2">角色列表</h3>
          <div className="grid grid-cols-2 gap-3">
            {game.scriptData?.roles?.map((role, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-lg ${
                  role.assignedTo?._id === user._id
                    ? 'bg-purple-500/30 border border-purple-500'
                    : 'bg-white/5'
                }`}
              >
                <div className="text-white font-semibold">{role.name}</div>
                {role.assignedTo && (
                  <div className="text-gray-400 text-sm">
                    {role.assignedTo.profile?.displayName || role.assignedTo.username}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {myRole?.clues && myRole.clues.length > 0 && (
          <div>
            <h3 className="text-xl font-bold text-white mb-2">你的线索</h3>
            <div className="space-y-2">
              {myRole.clues.map((clue, idx) => (
                <div key={idx} className="p-3 bg-white/5 rounded-lg">
                  <SparklesIcon className="w-5 h-5 text-yellow-400 inline mr-2" />
                  <span className="text-gray-300">{clue}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// Werewolf Game Component
const WerewolfGame = ({ game, user }) => {
  const myRole = game.werewolfData?.roles?.find(r => r.player?._id === user._id);

  return (
    <div className="mystery-card p-6">
      <h2 className="text-2xl font-bold text-white mb-4">狼人杀</h2>

      {myRole && (
        <div className="mb-6 p-4 bg-purple-500/20 border border-purple-500/50 rounded-lg">
          <h3 className="text-xl font-bold text-purple-300 mb-2">
            你的角色: {myRole.role === 'werewolf' ? '🐺 狼人' :
                      myRole.role === 'seer' ? '🔮 预言家' :
                      myRole.role === 'witch' ? '🧙 女巫' :
                      myRole.role === 'hunter' ? '🏹 猎人' : '👤 村民'}
          </h3>
          {myRole.alive ? (
            <span className="text-green-400">存活</span>
          ) : (
            <span className="text-red-400">已出局</span>
          )}
        </div>
      )}

      <div className="mb-4">
        <h3 className="text-white font-semibold mb-2">
          当前阶段: {game.werewolfData?.phase === 'night' ? '🌙 夜晚' : '☀️ 白天'}
        </h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {game.werewolfData?.roles?.map((role, idx) => (
          <div
            key={idx}
            className={`p-3 rounded-lg ${
              role.alive ? 'bg-white/5' : 'bg-red-500/20'
            } ${role.player?._id === user._id ? 'border-2 border-purple-500' : ''}`}
          >
            <div className="text-white font-semibold">
              {role.player?.profile?.displayName || role.player?.username}
            </div>
            <div className="text-gray-400 text-sm">
              {role.alive ? '存活' : '已出局'}
            </div>
          </div>
        ))}
      </div>

      {game.werewolfData?.events && game.werewolfData.events.length > 0 && (
        <div className="mt-6">
          <h3 className="text-white font-semibold mb-2">游戏记录</h3>
          <div className="space-y-2">
            {game.werewolfData.events.map((event, idx) => (
              <div key={idx} className="p-2 bg-white/5 rounded-lg text-gray-300 text-sm">
                {event.description}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default InteractiveGameRoom;
