import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import useAuthStore from '../store/authStore';
import socketService from '../services/socket';

const Chat = () => {
  const { matchId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [otherUser, setOtherUser] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const messagesEndRef = useRef(null);
  const typingTimeoutRef = useRef(null);

  useEffect(() => {
    // 加载聊天记录
    loadConversation();

    // 设置Socket监听
    socketService.onMessageReceived(handleMessageReceived);
    socketService.onTypingIndicator(handleTypingIndicator);
    socketService.onMessageRead(handleMessageRead);

    return () => {
      // 清理监听器
      socketService.removeAllListeners();
    };
  }, [matchId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const loadConversation = async () => {
    // 这里应该调用API加载对话历史
    // 暂时使用模拟数据
    setOtherUser({
      _id: 'other_user_id',
      username: '神秘人',
      profile: {
        displayName: '神秘人 #1234'
      }
    });
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleMessageReceived = (data) => {
    setMessages(prev => [...prev, {
      _id: data.messageId,
      sender: data.senderId,
      content: data.message.content.text,
      timestamp: new Date()
    }]);
    setIsTyping(false);
  };

  const handleTypingIndicator = (data) => {
    if (data.userId !== user._id) {
      setIsTyping(data.isTyping);
    }
  };

  const handleMessageRead = (data) => {
    // 更新消息已读状态
    console.log('Messages read:', data);
  };

  const handleInputChange = (e) => {
    setInputMessage(e.target.value);

    // 发送正在输入状态
    if (otherUser) {
      socketService.startTyping(otherUser._id);

      // 3秒后自动停止
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }

      typingTimeoutRef.current = setTimeout(() => {
        socketService.stopTyping(otherUser._id);
      }, 3000);
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();

    if (!inputMessage.trim()) return;

    // 停止输入状态
    if (otherUser) {
      socketService.stopTyping(otherUser._id);
    }

    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }

    // 立即显示消息（乐观更新）
    const tempMessage = {
      _id: Date.now().toString(),
      sender: user._id,
      content: inputMessage,
      timestamp: new Date(),
      status: 'sending'
    };

    setMessages(prev => [...prev, tempMessage]);
    setInputMessage('');

    // 发送消息
    socketService.sendMessage({
      conversationId,
      recipientId: otherUser._id,
      message: inputMessage
    });

    // 监听发送成功
    socketService.onMessageSent((data) => {
      setMessages(prev => prev.map(msg =>
        msg._id === tempMessage._id
          ? { ...msg, _id: data.messageId, status: 'sent' }
          : msg
      ));
    });
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-180px)] flex flex-col">
      {/* 聊天头部 */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mystery-card mb-4 flex items-center justify-between"
      >
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate(-1)}
            className="text-2xl hover:scale-110 transition-transform"
          >
            ←
          </button>

          <div className="w-12 h-12 rounded-full bg-gradient-mystery flex items-center justify-center text-2xl">
            👤
          </div>

          <div>
            <h2 className="font-bold">{otherUser?.profile?.displayName || '加载中...'}</h2>
            <p className="text-sm text-white/60">
              {isTyping ? '正在输入...' : '在线'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 transition-all text-sm"
            title="视频通话"
          >
            📹
          </button>
          <button
            className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 transition-all text-sm"
            title="更多"
          >
            ⋯
          </button>
        </div>
      </motion.div>

      {/* 聊天消息区域 */}
      <div className="flex-1 mystery-card overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-hide">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="text-6xl mb-4">💬</div>
                <p className="text-white/60">开始你们的对话吧</p>
              </div>
            </div>
          ) : (
            <AnimatePresence>
              {messages.map((message, index) => {
                const isOwn = message.sender === user._id;
                const showAvatar = index === 0 || messages[index - 1].sender !== message.sender;

                return (
                  <motion.div
                    key={message._id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    className={`flex ${isOwn ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`flex items-end space-x-2 max-w-[70%] ${isOwn ? 'flex-row-reverse space-x-reverse' : ''}`}>
                      {showAvatar && (
                        <div className="w-8 h-8 rounded-full bg-gradient-mystery flex items-center justify-center text-sm flex-shrink-0">
                          {isOwn ? user.username?.[0] : '?'}
                        </div>
                      )}

                      <div className={`flex flex-col ${isOwn ? 'items-end' : 'items-start'}`}>
                        <div className={isOwn ? 'chat-bubble-sent' : 'chat-bubble-received'}>
                          <p className="text-white/90">{message.content}</p>
                        </div>

                        <div className="flex items-center space-x-2 mt-1 px-2">
                          <span className="text-xs text-white/40">
                            {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </span>

                          {isOwn && message.status && (
                            <span className="text-xs text-white/40">
                              {message.status === 'sending' && '发送中'}
                              {message.status === 'sent' && '✓'}
                              {message.status === 'read' && '✓✓'}
                            </span>
                          )}
                        </div>
                      </div>

                      {!showAvatar && <div className="w-8" />}
                    </div>
                  </motion.div>
                );
              })}

              {isTyping && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
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
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <form onSubmit={handleSendMessage} className="border-t border-white/10 p-4">
          <div className="flex space-x-3">
            <button
              type="button"
              className="px-4 py-3 rounded-full bg-white/10 hover:bg-white/20 transition-all"
              title="表情"
            >
              😊
            </button>

            <input
              type="text"
              value={inputMessage}
              onChange={handleInputChange}
              placeholder="输入消息..."
              className="flex-1 mystery-input"
            />

            <button
              type="button"
              className="px-4 py-3 rounded-full bg-white/10 hover:bg-white/20 transition-all"
              title="图片"
            >
              📷
            </button>

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              type="submit"
              disabled={!inputMessage.trim()}
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

export default Chat;
