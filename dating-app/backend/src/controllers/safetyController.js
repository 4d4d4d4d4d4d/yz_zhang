import Block from '../models/Block.js';
import Report from '../models/Report.js';
import User from '../models/User.js';
import Match from '../models/Match.js';
import Conversation from '../models/Conversation.js';

// Block user
export const blockUser = async (req, res) => {
  try {
    const { userId } = req.params;
    const { reason, notes } = req.body;

    // Validate
    if (userId === req.userId) {
      return res.status(400).json({ error: '不能屏蔽自己' });
    }

    // Check if user exists
    const userToBlock = await User.findById(userId);
    if (!userToBlock) {
      return res.status(404).json({ error: '用户不存在' });
    }

    // Check if already blocked
    const existingBlock = await Block.findOne({
      blocker: req.userId,
      blocked: userId
    });

    if (existingBlock) {
      return res.status(400).json({ error: '已经屏蔽该用户' });
    }

    // Create block
    const block = new Block({
      blocker: req.userId,
      blocked: userId,
      reason,
      notes
    });

    await block.save();

    // Remove any existing matches
    await Match.deleteMany({
      $or: [
        { user1: req.userId, user2: userId },
        { user1: userId, user2: req.userId }
      ]
    });

    // Mark conversations as blocked
    await Conversation.updateMany(
      {
        $or: [
          { user1: req.userId, user2: userId },
          { user1: userId, user2: req.userId }
        ]
      },
      { isBlocked: true }
    );

    res.json({ message: '已屏蔽用户', block });
  } catch (error) {
    console.error('Block user error:', error);
    res.status(500).json({ error: '屏蔽用户失败' });
  }
};

// Unblock user
export const unblockUser = async (req, res) => {
  try {
    const { userId } = req.params;

    const result = await Block.findOneAndDelete({
      blocker: req.userId,
      blocked: userId
    });

    if (!result) {
      return res.status(404).json({ error: '未找到屏蔽记录' });
    }

    // Unblock conversations
    await Conversation.updateMany(
      {
        $or: [
          { user1: req.userId, user2: userId },
          { user1: userId, user2: req.userId }
        ]
      },
      { isBlocked: false }
    );

    res.json({ message: '已取消屏蔽' });
  } catch (error) {
    console.error('Unblock user error:', error);
    res.status(500).json({ error: '取消屏蔽失败' });
  }
};

// Get blocked users
export const getBlockedUsers = async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 20;
    const skip = (page - 1) * limit;

    const blocks = await Block.find({ blocker: req.userId })
      .populate('blocked', 'username profile.displayName profile.photos profile.aiAvatar')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit);

    const total = await Block.countDocuments({ blocker: req.userId });

    res.json({
      blocks,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get blocked users error:', error);
    res.status(500).json({ error: '获取屏蔽列表失败' });
  }
};

// Check if user is blocked
export const checkBlocked = async (req, res) => {
  try {
    const { userId } = req.params;

    const isBlocked = await Block.exists({
      blocker: req.userId,
      blocked: userId
    });

    const isBlockedBy = await Block.exists({
      blocker: userId,
      blocked: req.userId
    });

    res.json({
      isBlocked: !!isBlocked,
      isBlockedBy: !!isBlockedBy
    });
  } catch (error) {
    console.error('Check blocked error:', error);
    res.status(500).json({ error: '检查屏蔽状态失败' });
  }
};

// Report user
export const reportUser = async (req, res) => {
  try {
    const { userId } = req.params;
    const { type, reason, description, evidence, relatedContent } = req.body;

    // Validate
    if (userId === req.userId) {
      return res.status(400).json({ error: '不能举报自己' });
    }

    // Check if user exists
    const userToReport = await User.findById(userId);
    if (!userToReport) {
      return res.status(404).json({ error: '用户不存在' });
    }

    // Create report
    const report = new Report({
      reporter: req.userId,
      reported: userId,
      type: type || 'user',
      reason,
      description,
      evidence: evidence || [],
      relatedContent: relatedContent || {}
    });

    await report.save();

    // Update user's report count
    await User.findByIdAndUpdate(userId, {
      $inc: { 'moderation.reportCount': 1 }
    });

    res.json({ message: '举报已提交，感谢您的反馈', report });
  } catch (error) {
    console.error('Report user error:', error);
    res.status(500).json({ error: '提交举报失败' });
  }
};

// Get user's reports (reports they made)
export const getMyReports = async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 20;
    const skip = (page - 1) * limit;

    const reports = await Report.find({ reporter: req.userId })
      .populate('reported', 'username profile.displayName')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit);

    const total = await Report.countDocuments({ reporter: req.userId });

    res.json({
      reports,
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get my reports error:', error);
    res.status(500).json({ error: '获取举报记录失败' });
  }
};

// Cancel report (within 24 hours)
export const cancelReport = async (req, res) => {
  try {
    const { reportId } = req.params;

    const report = await Report.findOne({
      _id: reportId,
      reporter: req.userId,
      status: 'pending'
    });

    if (!report) {
      return res.status(404).json({ error: '未找到举报记录或已被处理' });
    }

    // Check if report is within 24 hours
    const hoursSinceReport = (Date.now() - report.createdAt) / (1000 * 60 * 60);
    if (hoursSinceReport > 24) {
      return res.status(400).json({ error: '只能撤销24小时内的举报' });
    }

    await Report.findByIdAndDelete(reportId);

    // Decrement report count
    await User.findByIdAndUpdate(report.reported, {
      $inc: { 'moderation.reportCount': -1 }
    });

    res.json({ message: '举报已撤销' });
  } catch (error) {
    console.error('Cancel report error:', error);
    res.status(500).json({ error: '撤销举报失败' });
  }
};
