import mongoose from 'mongoose';

const activitySchema = new mongoose.Schema({
  // 活动基本信息
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    required: true
  },
  type: {
    type: String,
    enum: [
      'camping', 'cafe-hopping', 'museum', 'escape-room', 'team-building',
      'hiking', 'concert', 'cooking-class', 'art-gallery', 'sports',
      'movie', 'karaoke', 'board-games', 'wine-tasting', 'photography-walk'
    ],
    required: true
  },

  // 时间和地点
  schedule: {
    startTime: {
      type: Date,
      required: true
    },
    endTime: {
      type: Date,
      required: true
    },
    duration: Number // 分钟
  },
  location: {
    name: String,
    address: String,
    city: String,
    coordinates: {
      lat: Number,
      lng: Number
    }
  },

  // 参与信息
  participants: {
    min: {
      type: Number,
      default: 2
    },
    max: {
      type: Number,
      default: 10
    },
    current: [{
      user: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      joinedAt: Date,
      status: {
        type: String,
        enum: ['confirmed', 'waitlist', 'cancelled'],
        default: 'confirmed'
      }
    }]
  },

  // 神秘盲盒模式
  mysteryMode: {
    enabled: {
      type: Boolean,
      default: true
    },
    revealTime: Date, // 活动前多久揭示参与者信息
    surpriseElement: String // 神秘惊喜
  },

  // 活动配置
  settings: {
    isPublic: {
      type: Boolean,
      default: true
    },
    requiresApproval: {
      type: Boolean,
      default: false
    },
    ageRestriction: {
      min: Number,
      max: Number
    },
    genderRatio: {
      male: Number,
      female: Number
    }
  },

  // 费用信息
  cost: {
    amount: {
      type: Number,
      default: 0
    },
    currency: {
      type: String,
      default: 'CNY'
    },
    includes: [String]
  },

  // 活动标签
  tags: [String],
  difficulty: {
    type: String,
    enum: ['easy', 'moderate', 'challenging'],
    default: 'easy'
  },

  // 活动状态
  status: {
    type: String,
    enum: ['draft', 'published', 'full', 'cancelled', 'completed'],
    default: 'published'
  },

  // 创建者
  organizer: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },
  isSystemGenerated: {
    type: Boolean,
    default: false
  },

  // 活动反馈
  feedback: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    rating: {
      type: Number,
      min: 1,
      max: 5
    },
    comment: String,
    photos: [String],
    submittedAt: Date
  }],

  // 照片墙
  gallery: [{
    url: String,
    uploadedBy: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    uploadedAt: Date
  }]
}, {
  timestamps: true
});

// 索引
activitySchema.index({ 'schedule.startTime': 1 });
activitySchema.index({ type: 1 });
activitySchema.index({ status: 1 });
activitySchema.index({ 'location.city': 1 });

// 检查活动是否已满
activitySchema.methods.isFull = function() {
  return this.participants.current.filter(p => p.status === 'confirmed').length >= this.participants.max;
};

// 添加参与者
activitySchema.methods.addParticipant = function(userId) {
  if (this.isFull()) {
    throw new Error('Activity is full');
  }

  this.participants.current.push({
    user: userId,
    joinedAt: new Date(),
    status: this.settings.requiresApproval ? 'waitlist' : 'confirmed'
  });

  return this;
};

// 计算平均评分
activitySchema.methods.getAverageRating = function() {
  if (this.feedback.length === 0) return 0;
  const sum = this.feedback.reduce((acc, f) => acc + f.rating, 0);
  return (sum / this.feedback.length).toFixed(1);
};

const Activity = mongoose.model('Activity', activitySchema);

export default Activity;
