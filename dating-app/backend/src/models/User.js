import mongoose from 'mongoose';
import bcrypt from 'bcryptjs';

const userSchema = new mongoose.Schema({
  // 基本信息
  username: {
    type: String,
    required: true,
    unique: true,
    trim: true,
    minlength: 3
  },
  email: {
    type: String,
    required: true,
    unique: true,
    lowercase: true,
    trim: true
  },
  password: {
    type: String,
    required: true,
    minlength: 6
  },

  // 个人资料
  profile: {
    displayName: String,
    age: {
      type: Number,
      min: 18,
      max: 100
    },
    gender: {
      type: String,
      enum: ['male', 'female', 'other', 'prefer-not-to-say']
    },
    bio: {
      type: String,
      maxlength: 500
    },
    location: {
      city: String,
      country: String
    },
    photos: [{
      url: String,
      isMain: Boolean
    }]
  },

  // AI化身配置
  aiAvatar: {
    personality: {
      type: String,
      enum: ['mysterious', 'cheerful', 'intellectual', 'adventurous', 'artistic', 'calm'],
      default: 'mysterious'
    },
    avatarStyle: {
      type: String,
      enum: ['abstract', 'anime', 'realistic', 'cartoon', 'cyberpunk'],
      default: 'abstract'
    },
    mysteryLevel: {
      type: Number,
      min: 1,
      max: 5,
      default: 3
    },
    voiceTone: {
      type: String,
      enum: ['warm', 'playful', 'serious', 'gentle', 'energetic'],
      default: 'warm'
    }
  },

  // 兴趣标签
  interests: [{
    type: String,
    enum: [
      'travel', 'reading', 'movies', 'music', 'sports', 'gaming',
      'cooking', 'art', 'photography', 'dancing', 'hiking', 'yoga',
      'technology', 'fashion', 'pets', 'wine', 'coffee', 'museums',
      'theater', 'camping', 'cycling', 'swimming', 'running', 'gym'
    ]
  }],

  // 特长技能
  talents: [{
    name: String,
    level: {
      type: String,
      enum: ['beginner', 'intermediate', 'advanced', 'expert']
    }
  }],

  // 情绪状态
  emotionalState: {
    current: {
      type: String,
      enum: ['happy', 'excited', 'calm', 'thoughtful', 'lonely', 'curious', 'adventurous'],
      default: 'calm'
    },
    history: [{
      mood: String,
      timestamp: Date,
      context: String
    }]
  },

  // 活动偏好
  activityPreferences: {
    preferredActivities: [{
      type: String,
      enum: ['camping', 'cafe-hopping', 'museum', 'escape-room', 'team-building',
             'hiking', 'concerts', 'cooking-class', 'art-gallery', 'sports']
    }],
    availability: {
      weekdays: Boolean,
      weekends: Boolean,
      evenings: Boolean
    },
    groupSize: {
      type: String,
      enum: ['one-on-one', 'small-group', 'large-group', 'any'],
      default: 'any'
    }
  },

  // 匹配偏好
  matchPreferences: {
    ageRange: {
      min: Number,
      max: Number
    },
    genderPreference: [{
      type: String,
      enum: ['male', 'female', 'other', 'any']
    }],
    distanceRange: {
      type: Number,
      default: 50 // km
    },
    mustHaveInterests: [String],
    dealBreakers: [String]
  },

  // 统计信息
  stats: {
    aiConversations: {
      type: Number,
      default: 0
    },
    matches: {
      type: Number,
      default: 0
    },
    activitiesAttended: {
      type: Number,
      default: 0
    },
    gamesPlayed: {
      type: Number,
      default: 0
    }
  },

  // 会员状态
  membership: {
    type: {
      type: String,
      enum: ['free', 'premium', 'vip'],
      default: 'free'
    },
    expiresAt: Date
  },

  // 账户状态
  isActive: {
    type: Boolean,
    default: true
  },
  isVerified: {
    type: Boolean,
    default: false
  },
  lastActive: {
    type: Date,
    default: Date.now
  }
}, {
  timestamps: true
});

// 密码加密中间件
userSchema.pre('save', async function(next) {
  if (!this.isModified('password')) return next();

  try {
    const salt = await bcrypt.genSalt(10);
    this.password = await bcrypt.hash(this.password, salt);
    next();
  } catch (error) {
    next(error);
  }
});

// 密码验证方法
userSchema.methods.comparePassword = async function(candidatePassword) {
  return await bcrypt.compare(candidatePassword, this.password);
};

// 获取公开资料（不包含敏感信息）
userSchema.methods.toPublicJSON = function() {
  const obj = this.toObject();
  delete obj.password;
  delete obj.email;
  delete obj.__v;
  return obj;
};

const User = mongoose.model('User', userSchema);

export default User;
