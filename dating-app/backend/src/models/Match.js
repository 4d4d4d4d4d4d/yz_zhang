import mongoose from 'mongoose';

const matchSchema = new mongoose.Schema({
  // 匹配的两个用户
  users: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  }],

  // 匹配分数
  compatibility: {
    overall: {
      type: Number,
      min: 0,
      max: 100
    },
    breakdown: {
      interests: Number,
      personality: Number,
      activities: Number,
      emotionalSync: Number
    }
  },

  // 匹配状态
  status: {
    type: String,
    enum: ['pending', 'accepted', 'rejected', 'expired', 'blocked'],
    default: 'pending'
  },

  // 神秘模式配置
  mysteryMode: {
    enabled: {
      type: Boolean,
      default: true
    },
    revealStage: {
      type: Number,
      min: 0,
      max: 5,
      default: 0 // 0=完全隐藏, 5=完全展示
    },
    unlockedInfo: [{
      type: String,
      enum: ['name', 'age', 'photo', 'interests', 'location', 'bio']
    }]
  },

  // 互动历史
  interactions: {
    messages: {
      type: Number,
      default: 0
    },
    gamesPlayed: [{
      gameName: String,
      playedAt: Date,
      result: mongoose.Schema.Types.Mixed
    }],
    sharedActivities: [{
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Activity'
    }]
  },

  // AI助手使用
  aiAssistance: {
    conversationTips: [{
      tip: String,
      usedAt: Date,
      wasHelpful: Boolean
    }],
    iceBreakers: [{
      suggestion: String,
      used: Boolean
    }]
  },

  // 时间戳
  matchedAt: {
    type: Date,
    default: Date.now
  },
  expiresAt: {
    type: Date,
    default: () => new Date(Date.now() + 7 * 24 * 60 * 60 * 1000) // 7天后过期
  },
  respondedAt: Date
}, {
  timestamps: true
});

// 索引优化
matchSchema.index({ users: 1 });
matchSchema.index({ status: 1 });
matchSchema.index({ matchedAt: -1 });

// 检查匹配是否过期
matchSchema.methods.isExpired = function() {
  return this.expiresAt < new Date();
};

// 升级神秘等级
matchSchema.methods.revealMoreInfo = function() {
  if (this.mysteryMode.enabled && this.mysteryMode.revealStage < 5) {
    this.mysteryMode.revealStage += 1;

    const revealOrder = [
      ['interests'],
      ['age'],
      ['location'],
      ['name'],
      ['photo'],
      ['bio']
    ];

    const toReveal = revealOrder[this.mysteryMode.revealStage - 1];
    this.mysteryMode.unlockedInfo.push(...toReveal);
  }
  return this;
};

const Match = mongoose.model('Match', matchSchema);

export default Match;
