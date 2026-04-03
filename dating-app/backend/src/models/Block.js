import mongoose from 'mongoose';

const blockSchema = new mongoose.Schema({
  blocker: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  blocked: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  reason: {
    type: String,
    enum: ['harassment', 'inappropriate', 'spam', 'fake', 'other'],
    required: true
  },
  notes: String,
  createdAt: {
    type: Date,
    default: Date.now
  }
});

// Compound index to ensure unique blocks and fast lookups
blockSchema.index({ blocker: 1, blocked: 1 }, { unique: true });
blockSchema.index({ blocker: 1 });
blockSchema.index({ blocked: 1 });

const Block = mongoose.model('Block', blockSchema);

export default Block;
