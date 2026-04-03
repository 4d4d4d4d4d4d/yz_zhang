import mongoose from 'mongoose';

const partyRoomSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true
  },
  description: String,

  host: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },

  type: {
    type: String,
    enum: ['voice', 'video', 'chat', 'music', 'game'],
    default: 'voice'
  },

  theme: {
    type: String,
    enum: ['casual', 'dating', 'music', 'gaming', 'study', 'night_chat', 'emotion_sharing', 'soul_mate'],
    default: 'casual'
  },

  // Voice/Video settings
  maxParticipants: {
    type: Number,
    default: 8,
    min: 2,
    max: 20
  },

  // Participants
  participants: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    role: {
      type: String,
      enum: ['host', 'admin', 'speaker', 'listener'],
      default: 'listener'
    },
    isMuted: {
      type: Boolean,
      default: false
    },
    isSpeaking: {
      type: Boolean,
      default: false
    },
    seatNumber: Number, // For voice rooms with seats
    joinedAt: {
      type: Date,
      default: Date.now
    }
  }],

  // Seats layout (for voice rooms)
  seats: [{
    number: Number,
    occupiedBy: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    isLocked: {
      type: Boolean,
      default: false
    }
  }],

  // Room settings
  settings: {
    isPrivate: {
      type: Boolean,
      default: false
    },
    password: String,
    requireApproval: {
      type: Boolean,
      default: false
    },
    allowGuests: {
      type: Boolean,
      default: true
    },
    muteNewcomers: {
      type: Boolean,
      default: false
    },
    genderRestriction: {
      type: String,
      enum: ['none', 'male', 'female', 'mixed'],
      default: 'none'
    }
  },

  // Room state
  status: {
    type: String,
    enum: ['active', 'paused', 'ended'],
    default: 'active'
  },

  // Background music (for music rooms)
  currentMusic: {
    title: String,
    artist: String,
    url: String,
    duration: Number,
    startedAt: Date
  },

  // Chat messages
  messages: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    content: String,
    type: {
      type: String,
      enum: ['text', 'emoji', 'gift', 'system'],
      default: 'text'
    },
    timestamp: {
      type: Date,
      default: Date.now
    }
  }],

  // Gifts/rewards
  gifts: [{
    sender: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    receiver: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    giftType: String,
    value: Number,
    timestamp: {
      type: Date,
      default: Date.now
    }
  }],

  // Room tags
  tags: [String],

  // Statistics
  stats: {
    totalJoins: {
      type: Number,
      default: 0
    },
    totalMessages: {
      type: Number,
      default: 0
    },
    totalDuration: {
      type: Number,
      default: 0 // in minutes
    },
    peakParticipants: {
      type: Number,
      default: 0
    }
  },

  // Moderation
  bannedUsers: [{
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  }],

  // Silent connection mode (Soul特色)
  silentMode: {
    enabled: {
      type: Boolean,
      default: false
    },
    description: String
  }
}, {
  timestamps: true
});

// Indexes
partyRoomSchema.index({ host: 1 });
partyRoomSchema.index({ status: 1, createdAt: -1 });
partyRoomSchema.index({ theme: 1, status: 1 });
partyRoomSchema.index({ 'settings.isPrivate': 1, status: 1 });

// Methods
partyRoomSchema.methods.addParticipant = function(userId, role = 'listener') {
  if (this.participants.length >= this.maxParticipants) {
    throw new Error('房间已满');
  }

  const exists = this.participants.some(p => p.user.toString() === userId.toString());
  if (exists) {
    throw new Error('已在房间中');
  }

  this.participants.push({
    user: userId,
    role,
    isMuted: this.settings.muteNewcomers
  });

  this.stats.totalJoins += 1;

  if (this.participants.length > this.stats.peakParticipants) {
    this.stats.peakParticipants = this.participants.length;
  }
};

partyRoomSchema.methods.removeParticipant = function(userId) {
  this.participants = this.participants.filter(
    p => p.user.toString() !== userId.toString()
  );

  // Free up seat if occupied
  const seat = this.seats.find(s => s.occupiedBy && s.occupiedBy.toString() === userId.toString());
  if (seat) {
    seat.occupiedBy = null;
  }
};

partyRoomSchema.methods.takeSeat = function(userId, seatNumber) {
  const seat = this.seats.find(s => s.number === seatNumber);
  if (!seat) {
    throw new Error('座位不存在');
  }

  if (seat.isLocked) {
    throw new Error('座位已锁定');
  }

  if (seat.occupiedBy) {
    throw new Error('座位已被占用');
  }

  seat.occupiedBy = userId;

  const participant = this.participants.find(p => p.user.toString() === userId.toString());
  if (participant) {
    participant.seatNumber = seatNumber;
    participant.role = 'speaker';
  }
};

partyRoomSchema.methods.leaveSeat = function(userId) {
  const seat = this.seats.find(s => s.occupiedBy && s.occupiedBy.toString() === userId.toString());
  if (seat) {
    seat.occupiedBy = null;
  }

  const participant = this.participants.find(p => p.user.toString() === userId.toString());
  if (participant) {
    participant.seatNumber = null;
    participant.role = 'listener';
  }
};

partyRoomSchema.methods.addMessage = function(userId, content, type = 'text') {
  this.messages.push({
    user: userId,
    content,
    type,
    timestamp: new Date()
  });

  this.stats.totalMessages += 1;

  // Keep only last 100 messages
  if (this.messages.length > 100) {
    this.messages = this.messages.slice(-100);
  }
};

const PartyRoom = mongoose.model('PartyRoom', partyRoomSchema);

export default PartyRoom;
