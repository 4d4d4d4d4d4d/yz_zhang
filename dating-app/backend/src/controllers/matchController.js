import Match from '../models/Match.js';
import User from '../models/User.js';
import aiService from '../services/aiService.js';

/**
 * 获取推荐匹配
 */
export const getRecommendations = async (req, res) => {
  try {
    const currentUser = req.user;
    const { limit = 10, mysteryMode = true } = req.query;

    // 查找潜在匹配用户
    const potentialMatches = await User.find({
      _id: { $ne: currentUser._id },
      isActive: true,
      'profile.gender': { $in: currentUser.matchPreferences.genderPreference || ['any'] },
      'profile.age': {
        $gte: currentUser.matchPreferences.ageRange?.min || 18,
        $lte: currentUser.matchPreferences.ageRange?.max || 100
      }
    }).limit(parseInt(limit) * 3); // 获取更多候选，然后排序

    // 排除已匹配的用户
    const existingMatches = await Match.find({
      users: currentUser._id,
      status: { $in: ['pending', 'accepted'] }
    }).select('users');

    const matchedUserIds = new Set(
      existingMatches.flatMap(m => m.users.map(u => u.toString()))
    );

    const unmatchedUsers = potentialMatches.filter(
      u => !matchedUserIds.has(u._id.toString())
    );

    // 计算兼容性分数
    const recommendations = await Promise.all(
      unmatchedUsers.map(async (user) => {
        const compatibility = await aiService.analyzeCompatibility(
          currentUser.toObject(),
          user.toObject()
        );

        // 如果开启神秘模式，隐藏部分信息
        let userInfo = user.toPublicJSON();
        if (mysteryMode === 'true' || mysteryMode === true) {
          userInfo = {
            _id: user._id,
            aiAvatar: user.aiAvatar,
            interests: user.interests.slice(0, 3), // 只显示3个兴趣
            profile: {
              age: user.profile.age,
              gender: user.profile.gender,
              bio: user.profile.bio?.substring(0, 50) + '...' // 只显示部分简介
            },
            mysteryLevel: user.aiAvatar.mysteryLevel
          };
        }

        return {
          user: userInfo,
          compatibility: compatibility.overall,
          breakdown: compatibility.breakdown,
          highlights: compatibility.highlights,
          iceBreakers: compatibility.iceBreakers
        };
      })
    );

    // 按兼容性排序
    recommendations.sort((a, b) => b.compatibility - a.compatibility);

    res.json({
      recommendations: recommendations.slice(0, parseInt(limit)),
      mysteryMode: mysteryMode === 'true' || mysteryMode === true
    });
  } catch (error) {
    console.error('Get Recommendations Error:', error);
    res.status(500).json({ error: 'Failed to get recommendations' });
  }
};

/**
 * 创建匹配请求
 */
export const createMatch = async (req, res) => {
  try {
    const { targetUserId } = req.body;
    const currentUser = req.user;

    // 检查目标用户是否存在
    const targetUser = await User.findById(targetUserId);
    if (!targetUser) {
      return res.status(404).json({ error: 'User not found' });
    }

    // 检查是否已存在匹配
    const existingMatch = await Match.findOne({
      users: { $all: [currentUser._id, targetUserId] }
    });

    if (existingMatch) {
      return res.status(400).json({
        error: 'Match already exists',
        match: existingMatch
      });
    }

    // 计算兼容性
    const compatibility = await aiService.analyzeCompatibility(
      currentUser.toObject(),
      targetUser.toObject()
    );

    // 创建新匹配
    const match = new Match({
      users: [currentUser._id, targetUserId],
      compatibility: {
        overall: compatibility.overall,
        breakdown: compatibility.breakdown
      },
      mysteryMode: {
        enabled: currentUser.aiAvatar.mysteryLevel >= 3,
        revealStage: 0,
        unlockedInfo: []
      },
      aiAssistance: {
        iceBreakers: compatibility.iceBreakers.map(suggestion => ({
          suggestion,
          used: false
        }))
      }
    });

    await match.save();

    // 更新用户统计
    currentUser.stats.matches += 1;
    await currentUser.save();

    res.status(201).json({
      message: 'Match created successfully',
      match,
      compatibility: compatibility.overall
    });
  } catch (error) {
    console.error('Create Match Error:', error);
    res.status(500).json({ error: 'Failed to create match' });
  }
};

/**
 * 响应匹配请求
 */
export const respondToMatch = async (req, res) => {
  try {
    const { matchId } = req.params;
    const { action } = req.body; // 'accept' or 'reject'

    const match = await Match.findById(matchId);
    if (!match) {
      return res.status(404).json({ error: 'Match not found' });
    }

    // 检查用户是否是匹配的参与者
    if (!match.users.some(u => u.toString() === req.userId.toString())) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    // 更新匹配状态
    match.status = action === 'accept' ? 'accepted' : 'rejected';
    match.respondedAt = new Date();

    await match.save();

    res.json({
      message: `Match ${action}ed successfully`,
      match
    });
  } catch (error) {
    console.error('Respond to Match Error:', error);
    res.status(500).json({ error: 'Failed to respond to match' });
  }
};

/**
 * 获取我的匹配列表
 */
export const getMyMatches = async (req, res) => {
  try {
    const { status } = req.query;

    const query = {
      users: req.userId
    };

    if (status) {
      query.status = status;
    }

    const matches = await Match.find(query)
      .populate('users', '-password -email')
      .sort({ matchedAt: -1 });

    res.json({ matches });
  } catch (error) {
    console.error('Get My Matches Error:', error);
    res.status(500).json({ error: 'Failed to get matches' });
  }
};

/**
 * 解锁神秘信息
 */
export const revealMysteryInfo = async (req, res) => {
  try {
    const { matchId } = req.params;

    const match = await Match.findById(matchId)
      .populate('users', '-password -email');

    if (!match) {
      return res.status(404).json({ error: 'Match not found' });
    }

    // 检查用户是否是匹配的参与者
    if (!match.users.some(u => u._id.toString() === req.userId.toString())) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    // 检查是否可以解锁（例如，基于互动次数）
    if (match.interactions.messages < match.mysteryMode.revealStage * 10) {
      return res.status(400).json({
        error: 'Need more interactions to reveal',
        requiredMessages: match.mysteryMode.revealStage * 10
      });
    }

    // 升级神秘等级
    match.revealMoreInfo();
    await match.save();

    res.json({
      message: 'Mystery info revealed',
      revealStage: match.mysteryMode.revealStage,
      unlockedInfo: match.mysteryMode.unlockedInfo,
      match
    });
  } catch (error) {
    console.error('Reveal Mystery Info Error:', error);
    res.status(500).json({ error: 'Failed to reveal mystery info' });
  }
};

/**
 * 获取匹配详情
 */
export const getMatchDetails = async (req, res) => {
  try {
    const { matchId } = req.params;

    const match = await Match.findById(matchId)
      .populate('users', '-password -email')
      .populate('interactions.sharedActivities');

    if (!match) {
      return res.status(404).json({ error: 'Match not found' });
    }

    // 检查用户是否是匹配的参与者
    if (!match.users.some(u => u._id.toString() === req.userId.toString())) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    // 根据神秘等级过滤信息
    const otherUser = match.users.find(u => u._id.toString() !== req.userId.toString());
    const revealedUser = { ...otherUser.toObject() };

    if (match.mysteryMode.enabled) {
      const unlocked = match.mysteryMode.unlockedInfo;

      if (!unlocked.includes('name')) {
        revealedUser.profile.displayName = '神秘人';
      }
      if (!unlocked.includes('photo')) {
        revealedUser.profile.photos = [];
      }
      if (!unlocked.includes('bio')) {
        revealedUser.profile.bio = revealedUser.profile.bio?.substring(0, 50) + '...';
      }
    }

    res.json({
      match: {
        ...match.toObject(),
        users: match.users.map(u =>
          u._id.toString() === req.userId.toString() ? u : revealedUser
        )
      }
    });
  } catch (error) {
    console.error('Get Match Details Error:', error);
    res.status(500).json({ error: 'Failed to get match details' });
  }
};
