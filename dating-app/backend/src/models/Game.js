import mongoose from 'mongoose';

const gameSchema = new mongoose.Schema({
  // 游戏类型
  type: {
    type: String,
    enum: ['truth-or-dare', 'personality-test', 'compatibility-quiz', 'ice-breaker-cards', 'would-you-rather'],
    required: true
  },

  // 游戏名称
  name: {
    type: String,
    required: true
  },

  // 游戏描述
  description: String,

  // 参与者
  participants: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    joinedAt: Date,
    status: {
      type: String,
      enum: ['active', 'finished', 'left'],
      default: 'active'
    }
  }],

  // 游戏会话
  session: {
    currentRound: {
      type: Number,
      default: 1
    },
    maxRounds: Number,
    currentTurn: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    questions: [{
      questionId: String,
      question: String,
      type: String, // 'truth', 'dare', 'choice', 'rating'
      askedBy: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      answeredBy: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      answer: mongoose.Schema.Types.Mixed,
      askedAt: Date,
      answeredAt: Date
    }]
  },

  // 性格测试结果
  personalityResults: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    answers: [mongoose.Schema.Types.Mixed],
    result: {
      type: String,
      traits: [String],
      description: String,
      compatibility: [{
        user: {
          type: mongoose.Schema.Types.ObjectId,
          ref: 'User'
        },
        score: Number
      }]
    },
    completedAt: Date
  }],

  // 游戏状态
  status: {
    type: String,
    enum: ['waiting', 'in-progress', 'completed', 'cancelled'],
    default: 'waiting'
  },

  // 游戏设置
  settings: {
    isPrivate: {
      type: Boolean,
      default: false
    },
    allowSpectators: {
      type: Boolean,
      default: false
    },
    timeLimit: Number, // 每回合时间限制（秒）
    difficulty: {
      type: String,
      enum: ['easy', 'medium', 'hard'],
      default: 'medium'
    }
  },

  // 创建者
  createdBy: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },

  // 关联匹配（如果是匹配对之间的游戏）
  relatedMatch: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Match'
  },

  // 统计信息
  stats: {
    totalQuestions: {
      type: Number,
      default: 0
    },
    averageResponseTime: Number,
    funRating: {
      type: Number,
      min: 0,
      max: 5
    }
  },

  // 时间戳
  startedAt: Date,
  completedAt: Date
}, {
  timestamps: true
});

// 索引
gameSchema.index({ participants: 1 });
gameSchema.index({ status: 1 });
gameSchema.index({ type: 1 });

// 添加参与者
gameSchema.methods.addParticipant = function(userId) {
  if (this.participants.some(p => p.user.toString() === userId.toString())) {
    throw new Error('User already in game');
  }

  this.participants.push({
    user: userId,
    joinedAt: new Date(),
    status: 'active'
  });

  return this;
};

// 移除参与者
gameSchema.methods.removeParticipant = function(userId) {
  const participant = this.participants.find(p => p.user.toString() === userId.toString());
  if (participant) {
    participant.status = 'left';
  }
  return this;
};

// 开始游戏
gameSchema.methods.startGame = function() {
  if (this.participants.length < 2) {
    throw new Error('Need at least 2 participants');
  }

  this.status = 'in-progress';
  this.startedAt = new Date();

  // 随机选择第一个玩家
  const randomIndex = Math.floor(Math.random() * this.participants.length);
  this.session.currentTurn = this.participants[randomIndex].user;

  return this;
};

// 下一回合
gameSchema.methods.nextTurn = function() {
  const activeParticipants = this.participants.filter(p => p.status === 'active');
  const currentIndex = activeParticipants.findIndex(
    p => p.user.toString() === this.session.currentTurn.toString()
  );

  const nextIndex = (currentIndex + 1) % activeParticipants.length;
  this.session.currentTurn = activeParticipants[nextIndex].user;
  this.session.currentRound += 1;

  return this;
};

// 添加问题和答案
gameSchema.methods.addQuestion = function(questionData) {
  this.session.questions.push({
    ...questionData,
    askedAt: new Date()
  });

  this.stats.totalQuestions += 1;

  return this;
};

// 记录答案
gameSchema.methods.recordAnswer = function(questionId, answer) {
  const question = this.session.questions.find(q => q.questionId === questionId);
  if (question) {
    question.answer = answer;
    question.answeredAt = new Date();
  }
  return this;
};

// 结束游戏
gameSchema.methods.finishGame = function() {
  this.status = 'completed';
  this.completedAt = new Date();
  this.participants.forEach(p => {
    if (p.status === 'active') {
      p.status = 'finished';
    }
  });
  return this;
};

const Game = mongoose.model('Game', gameSchema);

export default Game;
