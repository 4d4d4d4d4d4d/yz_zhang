import mongoose from 'mongoose';

const reportSchema = new mongoose.Schema({
  reporter: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  reported: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  type: {
    type: String,
    enum: ['user', 'message', 'activity', 'photo'],
    required: true,
    default: 'user'
  },
  reason: {
    type: String,
    enum: [
      'harassment',
      'inappropriate_content',
      'spam',
      'fake_profile',
      'scam',
      'underage',
      'violence',
      'hate_speech',
      'other'
    ],
    required: true
  },
  description: {
    type: String,
    required: true
  },
  evidence: [{
    type: String, // URLs to screenshots or other evidence
  }],
  relatedContent: {
    messageId: mongoose.Schema.Types.ObjectId,
    activityId: mongoose.Schema.Types.ObjectId,
    photoUrl: String
  },
  status: {
    type: String,
    enum: ['pending', 'reviewed', 'action_taken', 'dismissed'],
    default: 'pending'
  },
  reviewedBy: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User'
  },
  reviewNotes: String,
  actionTaken: {
    type: String,
    enum: ['warning', 'temporary_ban', 'permanent_ban', 'content_removed', 'none']
  },
  reviewedAt: Date,
  createdAt: {
    type: Date,
    default: Date.now
  }
});

// Indexes for efficient queries
reportSchema.index({ reporter: 1, createdAt: -1 });
reportSchema.index({ reported: 1, createdAt: -1 });
reportSchema.index({ status: 1, createdAt: -1 });

const Report = mongoose.model('Report', reportSchema);

export default Report;
