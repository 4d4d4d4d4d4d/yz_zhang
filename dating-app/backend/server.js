import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import mongoose from 'mongoose';
import { createServer } from 'http';
import { Server } from 'socket.io';

// 导入路由
import authRoutes from './src/routes/auth.js';
import aiRoutes from './src/routes/ai.js';
import matchRoutes from './src/routes/match.js';
import activityRoutes from './src/routes/activity.js';
import gameRoutes from './src/routes/game.js';

// 导入模型
import Conversation from './src/models/Conversation.js';
import Match from './src/models/Match.js';

// 加载环境变量
dotenv.config();

const app = express();
const httpServer = createServer(app);

// 配置Socket.io用于实时聊天
const io = new Server(httpServer, {
  cors: {
    origin: process.env.CLIENT_URL || 'http://localhost:5173',
    methods: ['GET', 'POST']
  }
});

// 中间件
app.use(cors({
  origin: process.env.CLIENT_URL || 'http://localhost:5173',
  credentials: true
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// 请求日志
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
  next();
});

// API路由
app.use('/api/auth', authRoutes);
app.use('/api/ai', aiRoutes);
app.use('/api/matches', matchRoutes);
app.use('/api/activities', activityRoutes);
app.use('/api/games', gameRoutes);

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'Dating App API'
  });
});

// 根路由
app.get('/', (req, res) => {
  res.json({
    message: '🌟 Welcome to Mystery Dating App API',
    version: '1.0.0',
    endpoints: {
      auth: '/api/auth',
      ai: '/api/ai',
      matches: '/api/matches',
      activities: '/api/activities'
    }
  });
});

// Socket.io实时聊天
const userSockets = new Map(); // 存储用户ID和socket ID的映射

io.on('connection', (socket) => {
  console.log('User connected:', socket.id);

  // 用户加入
  socket.on('user:join', (userId) => {
    userSockets.set(userId, socket.id);
    socket.userId = userId;
    console.log(`User ${userId} joined with socket ${socket.id}`);
  });

  // 发送消息
  socket.on('message:send', async (data) => {
    try {
      const { conversationId, recipientId, message } = data;

      // 查找或创建对话
      let conversation = await Conversation.findById(conversationId);

      if (!conversation) {
        conversation = new Conversation({
          type: 'user-to-user',
          participants: [socket.userId, recipientId]
        });
      }

      // 添加消息
      conversation.addMessage({
        sender: socket.userId,
        senderType: 'user',
        content: {
          text: message,
          type: 'text'
        }
      });

      await conversation.save();

      // 更新匹配的互动次数
      const match = await Match.findOne({
        users: { $all: [socket.userId, recipientId] }
      });

      if (match) {
        match.interactions.messages += 1;
        await match.save();
      }

      // 发送给接收者
      const recipientSocketId = userSockets.get(recipientId);
      if (recipientSocketId) {
        io.to(recipientSocketId).emit('message:received', {
          conversationId: conversation._id,
          message: conversation.messages[conversation.messages.length - 1],
          senderId: socket.userId
        });
      }

      // 确认发送成功
      socket.emit('message:sent', {
        conversationId: conversation._id,
        messageId: conversation.messages[conversation.messages.length - 1]._id
      });
    } catch (error) {
      console.error('Message send error:', error);
      socket.emit('message:error', { error: 'Failed to send message' });
    }
  });

  // 正在输入
  socket.on('typing:start', (data) => {
    const { recipientId } = data;
    const recipientSocketId = userSockets.get(recipientId);
    if (recipientSocketId) {
      io.to(recipientSocketId).emit('typing:indicator', {
        userId: socket.userId,
        isTyping: true
      });
    }
  });

  socket.on('typing:stop', (data) => {
    const { recipientId } = data;
    const recipientSocketId = userSockets.get(recipientId);
    if (recipientSocketId) {
      io.to(recipientSocketId).emit('typing:indicator', {
        userId: socket.userId,
        isTyping: false
      });
    }
  });

  // 标记消息已读
  socket.on('message:read', async (data) => {
    try {
      const { conversationId } = data;

      const conversation = await Conversation.findById(conversationId);
      if (conversation) {
        conversation.markAsRead(socket.userId);
        await conversation.save();

        // 通知发送者消息已读
        conversation.participants.forEach(participantId => {
          if (participantId.toString() !== socket.userId) {
            const socketId = userSockets.get(participantId.toString());
            if (socketId) {
              io.to(socketId).emit('message:read', {
                conversationId,
                readBy: socket.userId
              });
            }
          }
        });
      }
    } catch (error) {
      console.error('Mark read error:', error);
    }
  });

  // 断开连接
  socket.on('disconnect', () => {
    if (socket.userId) {
      userSockets.delete(socket.userId);
      console.log(`User ${socket.userId} disconnected`);
    }
  });
});

// 错误处理
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal server error',
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
  });
});

// 404处理
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

// 连接数据库并启动服务器
const PORT = process.env.PORT || 5000;
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/dating-app';

mongoose
  .connect(MONGODB_URI)
  .then(() => {
    console.log('✅ Connected to MongoDB');
    httpServer.listen(PORT, () => {
      console.log(`🚀 Server running on port ${PORT}`);
      console.log(`📡 API available at http://localhost:${PORT}`);
      console.log(`💬 Socket.io ready for real-time chat`);
    });
  })
  .catch((error) => {
    console.error('❌ MongoDB connection error:', error);
    process.exit(1);
  });

// 优雅关闭
process.on('SIGTERM', () => {
  console.log('SIGTERM signal received: closing HTTP server');
  httpServer.close(() => {
    console.log('HTTP server closed');
    mongoose.connection.close(false, () => {
      console.log('MongoDB connection closed');
      process.exit(0);
    });
  });
});

export default app;
