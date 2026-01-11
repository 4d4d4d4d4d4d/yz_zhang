import { io } from 'socket.io-client';

const SOCKET_URL = import.meta.env.VITE_API_URL?.replace('/api', '') || 'http://localhost:5000';

class SocketService {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
  }

  connect(userId) {
    if (this.socket?.connected) {
      return this.socket;
    }

    this.socket = io(SOCKET_URL, {
      transports: ['websocket'],
      autoConnect: true
    });

    this.socket.on('connect', () => {
      console.log('✅ Socket connected:', this.socket.id);
      if (userId) {
        this.socket.emit('user:join', userId);
      }
    });

    this.socket.on('disconnect', () => {
      console.log('❌ Socket disconnected');
    });

    this.socket.on('connect_error', (error) => {
      console.error('Socket connection error:', error);
    });

    return this.socket;
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  // 发送消息
  sendMessage(data) {
    if (this.socket?.connected) {
      this.socket.emit('message:send', data);
    }
  }

  // 监听接收消息
  onMessageReceived(callback) {
    if (this.socket) {
      this.socket.on('message:received', callback);
    }
  }

  // 监听消息发送确认
  onMessageSent(callback) {
    if (this.socket) {
      this.socket.on('message:sent', callback);
    }
  }

  // 监听消息错误
  onMessageError(callback) {
    if (this.socket) {
      this.socket.on('message:error', callback);
    }
  }

  // 发送正在输入状态
  startTyping(recipientId) {
    if (this.socket?.connected) {
      this.socket.emit('typing:start', { recipientId });
    }
  }

  stopTyping(recipientId) {
    if (this.socket?.connected) {
      this.socket.emit('typing:stop', { recipientId });
    }
  }

  // 监听对方输入状态
  onTypingIndicator(callback) {
    if (this.socket) {
      this.socket.on('typing:indicator', callback);
    }
  }

  // 标记消息已读
  markAsRead(conversationId) {
    if (this.socket?.connected) {
      this.socket.emit('message:read', { conversationId });
    }
  }

  // 监听消息已读
  onMessageRead(callback) {
    if (this.socket) {
      this.socket.on('message:read', callback);
    }
  }

  // 移除所有监听器
  removeAllListeners() {
    if (this.socket) {
      this.socket.removeAllListeners();
    }
  }
}

export default new SocketService();
