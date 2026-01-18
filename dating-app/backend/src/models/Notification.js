import mongoose from 'mongoose';

const notificationSchema = new mongoose.Schema({
  // 接收者
  recipient: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },

  // 发送者（可选，系统通知没有发送者）
  sender: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },

  // 通知类型
  type: {
    type: String,
    enum: [
      'new_match',           // 新匹配
      'match_accepted',      // 匹配被接受
      'new_message',         // 新消息
      'activity_invite',     // 活动邀请
      'activity_reminder',   // 活动提醒
      'activity_update',     // 活动更新
      'game_invite',         // 游戏邀请
      'game_turn',          // 游戏轮到你
      'profile_view',       // 有人查看了你的资料
      'interest_match',     // 兴趣匹配推荐
      'system'              // 系统通知
    ],
    required: true
  },

  // 通知标题
  title: {
    type: String,
    required: true
  },

  // 通知内容
  message: {
    type: String,
    required: true
  },

  // 关联数据
  relatedData: {
    matchId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Match'
    },
    activityId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Activity'
    },
    gameId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Game'
    },
    conversationId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Conversation'
    },
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    }
  },

  // 跳转链接
  actionUrl: String,

  // 通知状态
  isRead: {
    type: Boolean,
    default: false
  },
  readAt: Date,

  // 优先级
  priority: {
    type: String,
    enum: ['low', 'medium', 'high', 'urgent'],
    default: 'medium'
  },

  // 过期时间
  expiresAt: Date
}, {
  timestamps: true
});

// 索引
notificationSchema.index({ recipient: 1, isRead: 1 });
notificationSchema.index({ recipient: 1, createdAt: -1 });
notificationSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });

// 标记为已读
notificationSchema.methods.markAsRead = function() {
  this.isRead = true;
  this.readAt = new Date();
  return this;
};

// 静态方法：创建通知
notificationSchema.statics.createNotification = async function(data) {
  const notification = new this(data);
  await notification.save();

  // 这里可以触发实时推送
  // socket.io emit to recipient

  return notification;
};

// 静态方法：批量标记已读
notificationSchema.statics.markAllAsRead = async function(userId) {
  return await this.updateMany(
    { recipient: userId, isRead: false },
    { isRead: true, readAt: new Date() }
  );
};

// 静态方法：获取未读数量
notificationSchema.statics.getUnreadCount = async function(userId) {
  return await this.countDocuments({
    recipient: userId,
    isRead: false
  });
};

// 静态方法：清理过期通知
notificationSchema.statics.cleanExpired = async function() {
  return await this.deleteMany({
    expiresAt: { $lt: new Date() }
  });
};

const Notification = mongoose.model('Notification', notificationSchema);

export default Notification;
