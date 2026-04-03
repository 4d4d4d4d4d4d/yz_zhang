import Moment from '../models/Moment.js';
import User from '../models/User.js';
import Match from '../models/Match.js';
import Notification from '../models/Notification.js';

// Create moment
export const createMoment = async (req, res) => {
  try {
    const {
      content,
      type,
      mood,
      location,
      poll,
      visibility,
      tags,
      topics,
      anonymous,
      expiresAt
    } = req.body;

    const moment = new Moment({
      user: req.userId,
      content,
      type: type || 'text',
      mood,
      location,
      poll,
      visibility: visibility || 'public',
      tags: tags || [],
      topics: topics || [],
      anonymous: anonymous || false,
      expiresAt
    });

    await moment.save();
    await moment.populate('user', 'username profile.displayName profile.aiAvatar profile.photos');

    res.json({ message: '瞬间发布成功', moment });
  } catch (error) {
    console.error('Create moment error:', error);
    res.status(500).json({ error: '发布瞬间失败' });
  }
};

// Get moments feed
export const getMomentsFeed = async (req, res) => {
  try {
    const { page = 1, limit = 20, type, topic } = req.query;
    const skip = (page - 1) * limit;

    // Get user's matches for visibility filtering
    const userMatches = await Match.find({
      $or: [
        { user1: req.userId, status: 'accepted' },
        { user2: req.userId, status: 'accepted' }
      ]
    }).select('user1 user2');

    const matchedUserIds = userMatches.map(match =>
      match.user1.toString() === req.userId ? match.user2 : match.user1
    );

    // Build query
    const query = {
      $or: [
        { visibility: 'public' },
        { user: req.userId },
        { visibility: 'matches', user: { $in: matchedUserIds } }
      ]
    };

    if (type) {
      query.type = type;
    }

    if (topic) {
      query.topics = topic;
    }

    // Exclude expired moments
    query.$or.push({ expiresAt: { $exists: false } });
    query.$or.push({ expiresAt: { $gt: new Date() } });

    const moments = await Moment.find(query)
      .populate('user', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('comments.user', 'username profile.displayName profile.aiAvatar')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit));

    const total = await Moment.countDocuments(query);

    res.json({
      moments,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get moments feed error:', error);
    res.status(500).json({ error: '获取瞬间失败' });
  }
};

// Get user's moments
export const getUserMoments = async (req, res) => {
  try {
    const { userId } = req.params;
    const { page = 1, limit = 20 } = req.query;
    const skip = (page - 1) * limit;

    const moments = await Moment.find({ user: userId })
      .populate('user', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('comments.user', 'username profile.displayName profile.aiAvatar')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit));

    const total = await Moment.countDocuments({ user: userId });

    res.json({
      moments,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get user moments error:', error);
    res.status(500).json({ error: '获取用户瞬间失败' });
  }
};

// Get moment by ID
export const getMomentById = async (req, res) => {
  try {
    const { momentId } = req.params;

    const moment = await Moment.findById(momentId)
      .populate('user', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('comments.user', 'username profile.displayName profile.aiAvatar')
      .populate('likes.user', 'username profile.displayName profile.aiAvatar');

    if (!moment) {
      return res.status(404).json({ error: '瞬间不存在' });
    }

    // Increment view count
    moment.views += 1;
    await moment.save();

    res.json({ moment });
  } catch (error) {
    console.error('Get moment error:', error);
    res.status(500).json({ error: '获取瞬间详情失败' });
  }
};

// Toggle like
export const toggleLike = async (req, res) => {
  try {
    const { momentId } = req.params;

    const moment = await Moment.findById(momentId);
    if (!moment) {
      return res.status(404).json({ error: '瞬间不存在' });
    }

    const liked = moment.toggleLike(req.userId);
    await moment.save();

    // Create notification
    if (liked && moment.user.toString() !== req.userId) {
      await Notification.create({
        recipient: moment.user,
        sender: req.userId,
        type: 'moment_like',
        title: '有人喜欢了你的瞬间',
        message: '有人喜欢了你的瞬间',
        relatedData: {
          momentId: moment._id
        }
      });
    }

    await moment.populate('likes.user', 'username profile.displayName profile.aiAvatar');

    res.json({
      message: liked ? '点赞成功' : '取消点赞',
      liked,
      likeCount: moment.likes.length,
      likes: moment.likes
    });
  } catch (error) {
    console.error('Toggle like error:', error);
    res.status(500).json({ error: '操作失败' });
  }
};

// Add comment
export const addComment = async (req, res) => {
  try {
    const { momentId } = req.params;
    const { content } = req.body;

    if (!content || !content.trim()) {
      return res.status(400).json({ error: '评论内容不能为空' });
    }

    const moment = await Moment.findById(momentId);
    if (!moment) {
      return res.status(404).json({ error: '瞬间不存在' });
    }

    moment.addComment(req.userId, content);
    await moment.save();

    // Create notification
    if (moment.user.toString() !== req.userId) {
      await Notification.create({
        recipient: moment.user,
        sender: req.userId,
        type: 'moment_comment',
        title: '有人评论了你的瞬间',
        message: content.substring(0, 50),
        relatedData: {
          momentId: moment._id
        }
      });
    }

    await moment.populate('comments.user', 'username profile.displayName profile.aiAvatar');

    res.json({
      message: '评论成功',
      comment: moment.comments[moment.comments.length - 1],
      commentCount: moment.comments.length
    });
  } catch (error) {
    console.error('Add comment error:', error);
    res.status(500).json({ error: '评论失败' });
  }
};

// Delete comment
export const deleteComment = async (req, res) => {
  try {
    const { momentId, commentId } = req.params;

    const moment = await Moment.findById(momentId);
    if (!moment) {
      return res.status(404).json({ error: '瞬间不存在' });
    }

    const commentIndex = moment.comments.findIndex(
      c => c._id.toString() === commentId
    );

    if (commentIndex === -1) {
      return res.status(404).json({ error: '评论不存在' });
    }

    const comment = moment.comments[commentIndex];

    // Only comment owner or moment owner can delete
    if (
      comment.user.toString() !== req.userId &&
      moment.user.toString() !== req.userId
    ) {
      return res.status(403).json({ error: '无权删除此评论' });
    }

    moment.comments.splice(commentIndex, 1);
    await moment.save();

    res.json({ message: '评论已删除', commentCount: moment.comments.length });
  } catch (error) {
    console.error('Delete comment error:', error);
    res.status(500).json({ error: '删除评论失败' });
  }
};

// Vote on poll
export const voteOnPoll = async (req, res) => {
  try {
    const { momentId } = req.params;
    const { optionIndex } = req.body;

    const moment = await Moment.findById(momentId);
    if (!moment || moment.type !== 'poll' || !moment.poll) {
      return res.status(404).json({ error: '投票不存在' });
    }

    if (moment.poll.expiresAt && new Date() > moment.poll.expiresAt) {
      return res.status(400).json({ error: '投票已结束' });
    }

    if (optionIndex < 0 || optionIndex >= moment.poll.options.length) {
      return res.status(400).json({ error: '无效的选项' });
    }

    // Remove previous votes if not multiple choice
    if (!moment.poll.multipleChoice) {
      moment.poll.options.forEach(option => {
        option.votes = option.votes.filter(
          v => v.toString() !== req.userId
        );
      });
    }

    // Add new vote
    const option = moment.poll.options[optionIndex];
    const hasVoted = option.votes.some(v => v.toString() === req.userId);

    if (hasVoted) {
      // Remove vote
      option.votes = option.votes.filter(v => v.toString() !== req.userId);
    } else {
      // Add vote
      option.votes.push(req.userId);
    }

    await moment.save();

    res.json({
      message: hasVoted ? '已取消投票' : '投票成功',
      poll: moment.poll
    });
  } catch (error) {
    console.error('Vote on poll error:', error);
    res.status(500).json({ error: '投票失败' });
  }
};

// Delete moment
export const deleteMoment = async (req, res) => {
  try {
    const { momentId } = req.params;

    const moment = await Moment.findById(momentId);
    if (!moment) {
      return res.status(404).json({ error: '瞬间不存在' });
    }

    if (moment.user.toString() !== req.userId) {
      return res.status(403).json({ error: '无权删除此瞬间' });
    }

    await Moment.findByIdAndDelete(momentId);

    res.json({ message: '瞬间已删除' });
  } catch (error) {
    console.error('Delete moment error:', error);
    res.status(500).json({ error: '删除瞬间失败' });
  }
};

// Get trending topics
export const getTrendingTopics = async (req, res) => {
  try {
    const { limit = 10 } = req.query;

    // Get topics from last 7 days
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const topics = await Moment.aggregate([
      {
        $match: {
          createdAt: { $gte: sevenDaysAgo },
          topics: { $exists: true, $ne: [] }
        }
      },
      { $unwind: '$topics' },
      {
        $group: {
          _id: '$topics',
          count: { $sum: 1 },
          likeCount: { $sum: { $size: '$likes' } },
          commentCount: { $sum: { $size: '$comments' } }
        }
      },
      {
        $project: {
          topic: '$_id',
          count: 1,
          engagement: {
            $add: ['$likeCount', { $multiply: ['$commentCount', 2] }]
          }
        }
      },
      { $sort: { engagement: -1, count: -1 } },
      { $limit: parseInt(limit) }
    ]);

    res.json({ topics });
  } catch (error) {
    console.error('Get trending topics error:', error);
    res.status(500).json({ error: '获取热门话题失败' });
  }
};

// Get nearby moments
export const getNearbyMoments = async (req, res) => {
  try {
    const { longitude, latitude, maxDistance = 5000, page = 1, limit = 20 } = req.query;
    const skip = (page - 1) * limit;

    if (!longitude || !latitude) {
      return res.status(400).json({ error: '需要提供位置信息' });
    }

    const moments = await Moment.find({
      'location.coordinates': {
        $near: {
          $geometry: {
            type: 'Point',
            coordinates: [parseFloat(longitude), parseFloat(latitude)]
          },
          $maxDistance: parseInt(maxDistance)
        }
      },
      visibility: 'public'
    })
      .populate('user', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('comments.user', 'username profile.displayName profile.aiAvatar')
      .skip(skip)
      .limit(parseInt(limit));

    res.json({ moments });
  } catch (error) {
    console.error('Get nearby moments error:', error);
    res.status(500).json({ error: '获取附近瞬间失败' });
  }
};
