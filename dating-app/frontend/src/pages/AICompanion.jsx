import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import useAuthStore from '../store/authStore';
import { aiAPI } from '../services/api';

const AICompanion = () => {
  const { user } = useAuthStore();
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [currentEmotion, setCurrentEmotion] = useState('calm');
  const messagesEndRef = useRef(null);

  const quickStarters = [
    '今天心情有点低落...',
    '最近遇到了一些困惑',
    '想聊聊最近的生活',
    '给我一些约会建议吧',
    '我该怎么开启话题？'
  ];

  useEffect(() => {
    // 加载AI对话历史
    loadConversations();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const loadConversations = async () => {
    try {
      const res = await aiAPI.getConversations();
      if (res.data.conversations.length > 0) {
        const lastConversation = res.data.conversations[0];
        setMessages(
          lastConversation.messages.map(msg => ({
            role: msg.senderType === 'ai-companion' ? 'ai' : 'user',
            content: msg.content.text,
            emotion: msg.aiMetadata?.emotionDetected
          }))
        );
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const sendMessage = async (messageText) => {
    if (!messageText.trim()) return;

    const userMessage = {
      role: 'user',
      content: messageText,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setShowSuggestions(false);
    setIsTyping(true);

    try {
      const res = await aiAPI.companionChat(messageText);
      const aiMessage = {
        role: 'ai',
        content: res.data.message,
        emotion: res.data.emotion,
        suggestions: res.data.suggestions,
        timestamp: new Date()
      };

      setCurrentEmotion(res.data.emotion);
      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => [
        ...prev,
        {
          role: 'ai',
          content: '抱歉，我现在无法回应。请稍后再试。',
          timestamp: new Date()
        }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(inputMessage);
  };

  const handleQuickStart = (message) => {
    sendMessage(message);
  };

  const getEmotionColor = (emotion) => {
    const colors = {
      happy: 'from-yellow-400 to-orange-400',
      sad: 'from-blue-400 to-indigo-400',
      excited: 'from-pink-400 to-purple-400',
      anxious: 'from-gray-400 to-slate-400',
      romantic: 'from-rose-400 to-pink-400',
      calm: 'from-green-400 to-teal-400',
      neutral: 'from-purple-400 to-blue-400'
    };
    return colors[emotion] || colors.neutral;
  };

  const getEmotionEmoji = (emotion) => {
    const emojis = {
      happy: '😊',
      sad: '😢',
      excited: '🎉',
      anxious: '😰',
      romantic: '💕',
      calm: '😌',
      neutral: '🙂'
    };
    return emojis[emotion] || emojis.neutral;
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 h-[calc(100vh-180px)] flex flex-col">
      {/* AI伴侣头部 */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mystery-card mb-6 text-center"
      >
        <div className="flex items-center justify-center space-x-4">
          <motion.div
            animate={{
              scale: [1, 1.1, 1],
              rotate: [0, 5, -5, 0]
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              repeatType: 'reverse'
            }}
            className={`ai-avatar w-24 h-24 bg-gradient-to-br ${getEmotionColor(currentEmotion)}`}
          >
            <span className="text-4xl">{getEmotionEmoji(currentEmotion)}</span>
          </motion.div>

          <div className="text-left">
            <h2 className="text-2xl font-bold gradient-text mb-1">你的AI伴侣</h2>
            <p className="text-white/60 text-sm">
              {user?.aiAvatar?.personality === 'mysterious' && '神秘而温柔的陪伴'}
              {user?.aiAvatar?.personality === 'cheerful' && '阳光活力的伙伴'}
              {user?.aiAvatar?.personality === 'intellectual' && '理性睿智的导师'}
              {user?.aiAvatar?.personality === 'adventurous' && '冒险精神的同行者'}
              {user?.aiAvatar?.personality === 'artistic' && '艺术气息的知己'}
              {user?.aiAvatar?.personality === 'calm' && '平和沉静的倾听者'}
            </p>
            <div className="flex items-center space-x-2 mt-2">
              <span className="badge text-xs">24/7在线</span>
              <span className="badge text-xs">情感支持</span>
            </div>
          </div>
        </div>
      </motion.div>

      {/* 聊天区域 */}
      <div className="flex-1 mystery-card overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide">
          <AnimatePresence>
            {messages.length === 0 && showSuggestions && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="text-center space-y-6"
              >
                <div>
                  <h3 className="text-xl font-semibold mb-2">开始对话</h3>
                  <p className="text-white/60">我在这里倾听你的一切</p>
                </div>

                <div className="grid grid-cols-1 gap-3 max-w-md mx-auto">
                  {quickStarters.map((starter, index) => (
                    <motion.button
                      key={starter}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      whileHover={{ scale: 1.02, x: 5 }}
                      onClick={() => handleQuickStart(starter)}
                      className="p-4 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 hover:border-purple-400/50 transition-all text-left"
                    >
                      <span className="text-white/80">{starter}</span>
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}

            {messages.map((message, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={message.role === 'user' ? 'chat-bubble-sent' : 'chat-bubble-received'}>
                  <p className="text-white/90">{message.content}</p>
                  {message.emotion && (
                    <div className="mt-2 flex items-center space-x-2">
                      <span className="text-xs text-white/50">情绪：</span>
                      <span className="text-xs">{getEmotionEmoji(message.emotion)}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}

            {isTyping && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex justify-start"
              >
                <div className="chat-bubble-received">
                  <div className="flex space-x-2">
                    <motion.span
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1, repeat: Infinity, delay: 0 }}
                    >
                      ●
                    </motion.span>
                    <motion.span
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1, repeat: Infinity, delay: 0.2 }}
                    >
                      ●
                    </motion.span>
                    <motion.span
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1, repeat: Infinity, delay: 0.4 }}
                    >
                      ●
                    </motion.span>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <form onSubmit={handleSubmit} className="border-t border-white/10 p-4">
          <div className="flex space-x-3">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="输入消息..."
              className="flex-1 mystery-input"
              disabled={isTyping}
            />
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              type="submit"
              disabled={!inputMessage.trim() || isTyping}
              className="px-6 py-3 rounded-full bg-gradient-mystery disabled:opacity-50 disabled:cursor-not-allowed"
            >
              发送
            </motion.button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AICompanion;
