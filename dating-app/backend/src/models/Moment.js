import mongoose from 'mongoose';

const momentSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  content: {
    text: String,
    images: [String], // URLs
    video: String,
    audio: String
  },
  type: {
    type: String,
    enum: ['text', 'image', 'video', 'audio', 'thought', 'mood', 'poll'],
    default: 'text'
  },

  // Mood/emotion (Soul特色)
  mood: {
    emoji: String, // 😊, 😢, 😡, etc.
    label: String, // '开心', '难过', '生气'
    color: String  // mood color
  },

  // Location
  location: {
    name: String,
    coordinates: {
      type: {
        type: String,
        enum: ['Point'],
        default: 'Point'
      },
      coordinates: [Number] // [longitude, latitude]
    }
  },

  // Poll data
  poll: {
    question: String,
    options: [{
      text: String,
      votes: [{
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User'
      }]
    }],
    expiresAt: Date,
    multipleChoice: {
      type: Boolean,
      default: false
    }
  },

  // Interaction stats
  likes: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    timestamp: {
      type: Date,
      default: Date.now
    }
  }],

  comments: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    content: String,
    timestamp: {
      type: Date,
      default: Date.now
    },
    likes: [{
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    }]
  }],

  shares: [{
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User'
    },
    timestamp: {
      type: Date,
      default: Date.now
    }
  }],

  // Privacy settings
  visibility: {
    type: String,
    enum: ['public', 'friends', 'matches', 'private'],
    default: 'public'
  },

  // Tags and topics
  tags: [String],
  topics: [{
    type: String,
    index: true
  }],

  // Soul特色：匿名模式
  anonymous: {
    type: Boolean,
    default: false
  },

  // Content moderation
  isApproved: {
    type: Boolean,
    default: true
  },
  flagged: {
    type: Boolean,
    default: false
  },
  flagReasons: [String],

  // View count
  views: {
    type: Number,
    default: 0
  },

  // Expiration (for temporary moments)
  expiresAt: Date
}, {
  timestamps: true
});

// Indexes
momentSchema.index({ user: 1, createdAt: -1 });
momentSchema.index({ createdAt: -1 });
momentSchema.index({ topics: 1, createdAt: -1 });
momentSchema.index({ 'location.coordinates': '2dsphere' });
momentSchema.index({ visibility: 1, createdAt: -1 });
momentSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });

// Virtual for like count
momentSchema.virtual('likeCount').get(function() {
  return this.likes.length;
});

// Virtual for comment count
momentSchema.virtual('commentCount').get(function() {
  return this.comments.length;
});

// Virtual for share count
momentSchema.virtual('shareCount').get(function() {
  return this.shares.length;
});

// Methods
momentSchema.methods.toggleLike = function(userId) {
  const index = this.likes.findIndex(like => like.user.toString() === userId.toString());

  if (index > -1) {
    this.likes.splice(index, 1);
    return false; // unliked
  } else {
    this.likes.push({ user: userId });
    return true; // liked
  }
};

momentSchema.methods.addComment = function(userId, content) {
  this.comments.push({
    user: userId,
    content,
    timestamp: new Date()
  });
};

momentSchema.methods.canView = function(viewerId, viewerMatches = []) {
  if (this.visibility === 'public') return true;
  if (this.visibility === 'private' && this.user.toString() !== viewerId.toString()) return false;

  if (this.visibility === 'matches') {
    return viewerMatches.some(match =>
      match.toString() === this.user.toString()
    );
  }

  return false;
};

// Ensure virtuals are included in JSON
momentSchema.set('toJSON', { virtuals: true });
momentSchema.set('toObject', { virtuals: true });

const Moment = mongoose.model('Moment', momentSchema);

export default Moment;
