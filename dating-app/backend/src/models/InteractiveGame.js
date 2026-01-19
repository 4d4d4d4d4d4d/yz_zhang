import mongoose from 'mongoose';

const interactiveGameSchema = new mongoose.Schema({
  gameType: {
    type: String,
    enum: ['script_murder', 'draw_guess', 'werewolf', 'mafia', 'truth_dare', 'word_chain', 'riddle', 'karaoke'],
    required: true
  },
  title: {
    type: String,
    required: true
  },
  description: String,
  host: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  participants: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    role: String, // For script murder, werewolf, etc.
    score: {
      type: Number,
      default: 0
    },
    joinedAt: {
      type: Date,
      default: Date.now
    }
  }],
  maxParticipants: {
    type: Number,
    default: 8
  },
  minParticipants: {
    type: Number,
    default: 2
  },
  status: {
    type: String,
    enum: ['waiting', 'started', 'completed', 'cancelled'],
    default: 'waiting'
  },

  // Script Murder specific
  scriptData: {
    scriptId: String,
    theme: String, // 'mystery', 'romance', 'horror', 'comedy'
    difficulty: String, // 'easy', 'medium', 'hard'
    roles: [{
      name: String,
      description: String,
      assignedTo: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      }
    }],
    plot: String,
    clues: [{
      round: Number,
      clue: String,
      revealedAt: Date
    }],
    murderer: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    solution: String
  },

  // Draw & Guess specific
  drawGuessData: {
    rounds: [{
      roundNumber: Number,
      drawer: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      word: String,
      category: String,
      drawing: String, // Base64 or URL
      guesses: [{
        user: {
          type: mongoose.Schema.Types.ObjectId,
          ref: 'User'
        },
        guess: String,
        timestamp: Date,
        correct: Boolean
      }],
      timeLimit: {
        type: Number,
        default: 60 // seconds
      },
      startedAt: Date,
      completedAt: Date
    }],
    wordList: [String],
    currentRound: {
      type: Number,
      default: 0
    }
  },

  // Werewolf/Mafia specific
  werewolfData: {
    phase: String, // 'night', 'day', 'voting'
    dayCount: {
      type: Number,
      default: 1
    },
    roles: [{
      userId: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      role: String, // 'werewolf', 'villager', 'seer', 'doctor', 'hunter'
      alive: {
        type: Boolean,
        default: true
      }
    }],
    events: [{
      phase: String,
      day: Number,
      action: String, // 'kill', 'save', 'vote', 'check'
      actor: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      target: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      timestamp: Date
    }],
    votes: [{
      voter: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      },
      target: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      }
    }]
  },

  // Common game data
  currentTurn: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },
  chat: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    message: String,
    timestamp: {
      type: Date,
      default: Date.now
    },
    type: {
      type: String,
      enum: ['text', 'system', 'drawing', 'guess'],
      default: 'text'
    }
  }],

  settings: {
    isPrivate: {
      type: Boolean,
      default: false
    },
    password: String,
    allowSpectators: {
      type: Boolean,
      default: true
    },
    language: {
      type: String,
      default: 'zh-CN'
    }
  },

  startedAt: Date,
  completedAt: Date,
  duration: Number, // in minutes

  winner: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },
  results: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    score: Number,
    rank: Number,
    achievements: [String]
  }],

  ratings: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    rating: {
      type: Number,
      min: 1,
      max: 5
    },
    comment: String
  }]
}, {
  timestamps: true
});

// Indexes
interactiveGameSchema.index({ gameType: 1, status: 1, createdAt: -1 });
interactiveGameSchema.index({ host: 1 });
interactiveGameSchema.index({ 'participants.user': 1 });
interactiveGameSchema.index({ status: 1, createdAt: -1 });

// Methods
interactiveGameSchema.methods.addParticipant = function(userId, role = null) {
  if (this.participants.length >= this.maxParticipants) {
    throw new Error('Game is full');
  }

  const exists = this.participants.some(p => p.user.toString() === userId.toString());
  if (exists) {
    throw new Error('User already in game');
  }

  this.participants.push({ user: userId, role });
};

interactiveGameSchema.methods.removeParticipant = function(userId) {
  this.participants = this.participants.filter(
    p => p.user.toString() !== userId.toString()
  );
};

interactiveGameSchema.methods.canStart = function() {
  return this.participants.length >= this.minParticipants &&
         this.participants.length <= this.maxParticipants;
};

const InteractiveGame = mongoose.model('InteractiveGame', interactiveGameSchema);

export default InteractiveGame;
