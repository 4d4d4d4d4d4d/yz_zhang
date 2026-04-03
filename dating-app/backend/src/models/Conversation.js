import mongoose from 'mongoose';

const messageSchema = new mongoose.Schema({
  sender: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },
  senderType: {
    type: String,
    enum: ['user', 'ai-companion'],
    default: 'user'
  },
  content: {
    text: String,
    type: {
      type: String,
      enum: ['text', 'image', 'voice', 'emoji', 'game-invite', 'activity-invite'],
      default: 'text'
    },
    mediaUrl: String
  },

  // AI辅助信息
  aiMetadata: {
    emotionDetected: {
      type: String,
      enum: ['happy', 'sad', 'excited', 'anxious', 'confused', 'romantic', 'neutral']
    },
    sentiment: {
      type: Number,
      min: -1,
      max: 1
    },
    suggestedResponses: [String],
    conversationTips: [String]
  },

  // 消息状态
  isRead: {
    type: Boolean,
    default: false
  },
  readAt: Date,

  timestamp: {
    type: Date,
    default: Date.now
  }
});

const conversationSchema = new mongoose.Schema({
  // 对话类型
  type: {
    type: String,
    enum: ['user-to-user', 'user-to-ai', 'group'],
    required: true
  },

  // 参与者
  participants: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  }],

  // 关联匹配（如果是匹配产生的对话）
  relatedMatch: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Match'
  },

  // 消息列表
  messages: [messageSchema],

  // AI伴侣配置（用于AI对话）
  aiCompanion: {
    personality: String,
    role: {
      type: String,
      enum: ['emotional-support', 'dating-coach', 'conversation-practice', 'friend'],
      default: 'emotional-support'
    },
    context: String // AI记住的用户上下文
  },

  // 对话分析
  analytics: {
    totalMessages: {
      type: Number,
      default: 0
    },
    averageResponseTime: Number, // 秒
    emotionalTrend: [{
      emotion: String,
      count: Number
    }],
    conversationQuality: {
      type: Number,
      min: 0,
      max: 100
    },
    engagementScore: {
      type: Number,
      min: 0,
      max: 100
    }
  },

  // 对话状态
  isActive: {
    type: Boolean,
    default: true
  },
  lastMessageAt: {
    type: Date,
    default: Date.now
  },

  // 特殊标记
  isPinned: {
    type: Boolean,
    default: false
  },
  isMuted: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  }]
}, {
  timestamps: true
});

// 索引
conversationSchema.index({ participants: 1 });
conversationSchema.index({ lastMessageAt: -1 });
conversationSchema.index({ type: 1 });

// 添加消息
conversationSchema.methods.addMessage = function(messageData) {
  this.messages.push(messageData);
  this.lastMessageAt = new Date();
  this.analytics.totalMessages += 1;
  return this;
};

// 获取未读消息数
conversationSchema.methods.getUnreadCount = function(userId) {
  return this.messages.filter(m =>
    !m.isRead &&
    m.sender.toString() !== userId.toString()
  ).length;
};

// 标记所有消息为已读
conversationSchema.methods.markAsRead = function(userId) {
  this.messages.forEach(m => {
    if (m.sender.toString() !== userId.toString() && !m.isRead) {
      m.isRead = true;
      m.readAt = new Date();
    }
  });
  return this;
};

// 计算对话质量分数
conversationSchema.methods.calculateQuality = function() {
  if (this.messages.length < 10) return 0;

  let score = 50; // 基础分

  // 基于消息数量
  if (this.messages.length > 50) score += 10;
  if (this.messages.length > 100) score += 10;

  // 基于情绪多样性
  const emotions = new Set(this.messages.map(m => m.aiMetadata?.emotionDetected).filter(Boolean));
  score += emotions.size * 5;

  // 基于回复速度
  if (this.analytics.averageResponseTime < 300) score += 10; // 5分钟内
  if (this.analytics.averageResponseTime < 60) score += 10; // 1分钟内

  return Math.min(score, 100);
};

const Conversation = mongoose.model('Conversation', conversationSchema);

export default Conversation;
