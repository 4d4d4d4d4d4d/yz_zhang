import User from '../models/User.js';
import Match from '../models/Match.js';
import aiService from '../services/aiService.js';

/**
 * 搜索用户
 */
export const searchUsers = async (req, res) => {
  try {
    const {
      keyword,
      gender,
      minAge,
      maxAge,
      interests,
      city,
      page = 1,
      limit = 20
    } = req.query;

    const query = {
      _id: { $ne: req.userId }, // 排除自己
      isActive: true
    };

    // 关键词搜索（用户名或显示名称）
    if (keyword) {
      query.$or = [
        { username: { $regex: keyword, $options: 'i' } },
        { 'profile.displayName': { $regex: keyword, $options: 'i' } }
      ];
    }

    // 性别筛选
    if (gender && gender !== 'any') {
      query['profile.gender'] = gender;
    }

    // 年龄筛选
    if (minAge || maxAge) {
      query['profile.age'] = {};
      if (minAge) query['profile.age'].$gte = parseInt(minAge);
      if (maxAge) query['profile.age'].$lte = parseInt(maxAge);
    }

    // 兴趣筛选
    if (interests) {
      const interestArray = Array.isArray(interests) ? interests : [interests];
      query.interests = { $in: interestArray };
    }

    // 城市筛选
    if (city) {
      query['profile.location.city'] = city;
    }

    const users = await User.find(query)
      .select('-password -email')
      .sort({ lastActive: -1 })
      .limit(parseInt(limit))
      .skip((parseInt(page) - 1) * parseInt(limit));

    const total = await User.countDocuments(query);

    // 获取已匹配的用户ID列表
    const existingMatches = await Match.find({
      users: req.userId
    }).select('users');

    const matchedUserIds = new Set(
      existingMatches.flatMap(m =>
        m.users.map(u => u.toString()).filter(id => id !== req.userId.toString())
      )
    );

    // 标记已匹配的用户
    const usersWithMatchStatus = users.map(user => ({
      ...user.toObject(),
      isMatched: matchedUserIds.has(user._id.toString())
    }));

    res.json({
      users: usersWithMatchStatus,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / parseInt(limit))
      }
    });
  } catch (error) {
    console.error('Search Users Error:', error);
    res.status(500).json({ error: 'Failed to search users' });
  }
};

/**
 * 获取推荐用户（基于算法）
 */
export const getRecommendedUsers = async (req, res) => {
  try {
    const { limit = 10 } = req.query;
    const currentUser = req.user;

    // 基于匹配偏好查找用户
    const query = {
      _id: { $ne: currentUser._id },
      isActive: true
    };

    // 应用匹配偏好
    if (currentUser.matchPreferences?.genderPreference?.length > 0) {
      const genderPref = currentUser.matchPreferences.genderPreference;
      if (!genderPref.includes('any')) {
        query['profile.gender'] = { $in: genderPref };
      }
    }

    if (currentUser.matchPreferences?.ageRange) {
      query['profile.age'] = {
        $gte: currentUser.matchPreferences.ageRange.min || 18,
        $lte: currentUser.matchPreferences.ageRange.max || 100
      };
    }

    // 共同兴趣加分
    if (currentUser.interests?.length > 0) {
      query.interests = { $in: currentUser.interests };
    }

    const users = await User.find(query)
      .select('-password -email')
      .limit(parseInt(limit) * 3);

    // 排除已匹配的用户
    const existingMatches = await Match.find({
      users: currentUser._id
    }).select('users');

    const matchedUserIds = new Set(
      existingMatches.flatMap(m => m.users.map(u => u.toString()))
    );

    const unmatchedUsers = users.filter(
      u => !matchedUserIds.has(u._id.toString())
    );

    // 计算兼容性并排序
    const recommendations = await Promise.all(
      unmatchedUsers.map(async (user) => {
        const compatibility = await aiService.analyzeCompatibility(
          currentUser.toObject(),
          user.toObject()
        );

        return {
          user: user.toObject(),
          compatibility: compatibility.overall,
          commonInterests: currentUser.interests?.filter(i =>
            user.interests?.includes(i)
          ) || []
        };
      })
    );

    recommendations.sort((a, b) => b.compatibility - a.compatibility);

    res.json({
      users: recommendations.slice(0, parseInt(limit))
    });
  } catch (error) {
    console.error('Get Recommended Users Error:', error);
    res.status(500).json({ error: 'Failed to get recommended users' });
  }
};

/**
 * 获取用户详情（公开信息）
 */
export const getUserProfile = async (req, res) => {
  try {
    const { userId } = req.params;

    const user = await User.findById(userId)
      .select('-password -email');

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // 检查是否已匹配
    const match = await Match.findOne({
      users: { $all: [req.userId, userId] }
    });

    // 根据神秘模式过滤信息
    let userProfile = user.toPublicJSON();

    if (match && match.mysteryMode?.enabled) {
      const unlocked = match.mysteryMode.unlockedInfo;

      if (!unlocked.includes('name')) {
        userProfile.profile.displayName = '神秘人';
        userProfile.username = `user_${user._id.toString().slice(-6)}`;
      }
      if (!unlocked.includes('photo')) {
        userProfile.profile.photos = [];
      }
      if (!unlocked.includes('age')) {
        userProfile.profile.age = null;
      }
    }

    res.json({
      user: userProfile,
      isMatched: !!match,
      matchStatus: match?.status || null
    });
  } catch (error) {
    console.error('Get User Profile Error:', error);
    res.status(500).json({ error: 'Failed to get user profile' });
  }
};

/**
 * 获取在线用户列表
 */
export const getOnlineUsers = async (req, res) => {
  try {
    const { limit = 20 } = req.query;

    // 最近5分钟活跃的用户
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);

    const users = await User.find({
      _id: { $ne: req.userId },
      isActive: true,
      lastActive: { $gte: fiveMinutesAgo }
    })
      .select('-password -email')
      .sort({ lastActive: -1 })
      .limit(parseInt(limit));

    res.json({ users });
  } catch (error) {
    console.error('Get Online Users Error:', error);
    res.status(500).json({ error: 'Failed to get online users' });
  }
};

/**
 * 获取附近的用户（基于城市）
 */
export const getNearbyUsers = async (req, res) => {
  try {
    const { limit = 20 } = req.query;
    const currentUser = req.user;

    if (!currentUser.profile?.location?.city) {
      return res.status(400).json({ error: 'Location not set' });
    }

    const users = await User.find({
      _id: { $ne: currentUser._id },
      isActive: true,
      'profile.location.city': currentUser.profile.location.city
    })
      .select('-password -email')
      .sort({ lastActive: -1 })
      .limit(parseInt(limit));

    res.json({ users });
  } catch (error) {
    console.error('Get Nearby Users Error:', error);
    res.status(500).json({ error: 'Failed to get nearby users' });
  }
};

/**
 * 获取热门用户
 */
export const getPopularUsers = async (req, res) => {
  try {
    const { limit = 20 } = req.query;

    const users = await User.find({
      _id: { $ne: req.userId },
      isActive: true,
      isVerified: true
    })
      .select('-password -email')
      .sort({
        'stats.matches': -1,
        'stats.activitiesAttended': -1,
        lastActive: -1
      })
      .limit(parseInt(limit));

    res.json({ users });
  } catch (error) {
    console.error('Get Popular Users Error:', error);
    res.status(500).json({ error: 'Failed to get popular users' });
  }
};
