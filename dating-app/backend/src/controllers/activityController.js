import Activity from '../models/Activity.js';
import User from '../models/User.js';

/**
 * 获取活动列表
 */
export const getActivities = async (req, res) => {
  try {
    const {
      type,
      city,
      startDate,
      endDate,
      mysteryMode,
      limit = 20,
      page = 1
    } = req.query;

    const query = {
      status: 'published',
      'schedule.startTime': { $gte: new Date() }
    };

    if (type) query.type = type;
    if (city) query['location.city'] = city;
    if (startDate) query['schedule.startTime'].$gte = new Date(startDate);
    if (endDate) query['schedule.startTime'].$lte = new Date(endDate);
    if (mysteryMode) query['mysteryMode.enabled'] = mysteryMode === 'true';

    const activities = await Activity.find(query)
      .populate('organizer', 'username profile.displayName')
      .sort({ 'schedule.startTime': 1 })
      .limit(parseInt(limit))
      .skip((parseInt(page) - 1) * parseInt(limit));

    const total = await Activity.countDocuments(query);

    res.json({
      activities,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / parseInt(limit))
      }
    });
  } catch (error) {
    console.error('Get Activities Error:', error);
    res.status(500).json({ error: 'Failed to get activities' });
  }
};

/**
 * 创建活动
 */
export const createActivity = async (req, res) => {
  try {
    const activityData = {
      ...req.body,
      organizer: req.userId,
      isSystemGenerated: false
    };

    const activity = new Activity(activityData);
    await activity.save();

    res.status(201).json({
      message: 'Activity created successfully',
      activity
    });
  } catch (error) {
    console.error('Create Activity Error:', error);
    res.status(500).json({ error: 'Failed to create activity' });
  }
};

/**
 * 获取活动详情
 */
export const getActivityDetails = async (req, res) => {
  try {
    const { activityId } = req.params;

    const activity = await Activity.findById(activityId)
      .populate('organizer', 'username profile.displayName profile.photos')
      .populate('participants.current.user', 'username profile.displayName aiAvatar');

    if (!activity) {
      return res.status(404).json({ error: 'Activity not found' });
    }

    // 如果是神秘模式且未到揭示时间，隐藏参与者信息
    let participants = activity.participants.current;
    if (
      activity.mysteryMode.enabled &&
      activity.mysteryMode.revealTime &&
      new Date() < activity.mysteryMode.revealTime
    ) {
      participants = participants.map(p => ({
        ...p.toObject(),
        user: {
          _id: p.user._id,
          aiAvatar: p.user.aiAvatar,
          mysteryProfile: true
        }
      }));
    }

    res.json({
      ...activity.toObject(),
      participants: {
        ...activity.participants.toObject(),
        current: participants
      },
      averageRating: activity.getAverageRating(),
      isParticipating: activity.participants.current.some(
        p => p.user._id.toString() === req.userId.toString()
      )
    });
  } catch (error) {
    console.error('Get Activity Details Error:', error);
    res.status(500).json({ error: 'Failed to get activity details' });
  }
};

/**
 * 报名参加活动
 */
export const joinActivity = async (req, res) => {
  try {
    const { activityId } = req.params;

    const activity = await Activity.findById(activityId);
    if (!activity) {
      return res.status(404).json({ error: 'Activity not found' });
    }

    // 检查活动状态
    if (activity.status !== 'published') {
      return res.status(400).json({ error: 'Activity is not available' });
    }

    // 检查是否已报名
    const alreadyJoined = activity.participants.current.some(
      p => p.user.toString() === req.userId.toString()
    );

    if (alreadyJoined) {
      return res.status(400).json({ error: 'Already joined this activity' });
    }

    // 检查是否已满
    if (activity.isFull()) {
      return res.status(400).json({ error: 'Activity is full' });
    }

    // 添加参与者
    activity.addParticipant(req.userId);

    // 如果满了，更新状态
    if (activity.isFull()) {
      activity.status = 'full';
    }

    await activity.save();

    // 更新用户统计
    req.user.stats.activitiesAttended += 1;
    await req.user.save();

    res.json({
      message: 'Successfully joined activity',
      activity
    });
  } catch (error) {
    console.error('Join Activity Error:', error);
    res.status(500).json({ error: error.message || 'Failed to join activity' });
  }
};

/**
 * 取消报名
 */
export const leaveActivity = async (req, res) => {
  try {
    const { activityId } = req.params;

    const activity = await Activity.findById(activityId);
    if (!activity) {
      return res.status(404).json({ error: 'Activity not found' });
    }

    // 查找并移除参与者
    const participantIndex = activity.participants.current.findIndex(
      p => p.user.toString() === req.userId.toString()
    );

    if (participantIndex === -1) {
      return res.status(400).json({ error: 'Not a participant' });
    }

    activity.participants.current.splice(participantIndex, 1);

    // 如果之前是满的，现在有空位了
    if (activity.status === 'full') {
      activity.status = 'published';
    }

    await activity.save();

    res.json({
      message: 'Successfully left activity',
      activity
    });
  } catch (error) {
    console.error('Leave Activity Error:', error);
    res.status(500).json({ error: 'Failed to leave activity' });
  }
};

/**
 * 随机匹配活动
 */
export const getRandomActivity = async (req, res) => {
  try {
    const user = req.user;

    // 基于用户偏好筛选活动
    const query = {
      status: 'published',
      'schedule.startTime': { $gte: new Date() }
    };

    // 如果用户有活动偏好
    if (user.activityPreferences?.preferredActivities?.length > 0) {
      query.type = { $in: user.activityPreferences.preferredActivities };
    }

    // 如果用户有位置信息
    if (user.profile?.location?.city) {
      query['location.city'] = user.profile.location.city;
    }

    // 获取所有符合条件的活动
    const activities = await Activity.find(query);

    if (activities.length === 0) {
      return res.status(404).json({ error: 'No activities available' });
    }

    // 随机选择一个
    const randomIndex = Math.floor(Math.random() * activities.length);
    const randomActivity = activities[randomIndex];

    await randomActivity.populate('organizer', 'username profile.displayName');

    res.json({
      activity: randomActivity,
      message: '为你找到了一个神秘活动！',
      mysteryElement: randomActivity.mysteryMode.surpriseElement || '等待你的到来...'
    });
  } catch (error) {
    console.error('Get Random Activity Error:', error);
    res.status(500).json({ error: 'Failed to get random activity' });
  }
};

/**
 * 提交活动反馈
 */
export const submitFeedback = async (req, res) => {
  try {
    const { activityId } = req.params;
    const { rating, comment, photos } = req.body;

    const activity = await Activity.findById(activityId);
    if (!activity) {
      return res.status(404).json({ error: 'Activity not found' });
    }

    // 检查用户是否参加了活动
    const isParticipant = activity.participants.current.some(
      p => p.user.toString() === req.userId.toString()
    );

    if (!isParticipant) {
      return res.status(403).json({ error: 'You did not participate in this activity' });
    }

    // 检查是否已提交反馈
    const existingFeedback = activity.feedback.find(
      f => f.user.toString() === req.userId.toString()
    );

    if (existingFeedback) {
      return res.status(400).json({ error: 'Feedback already submitted' });
    }

    // 添加反馈
    activity.feedback.push({
      user: req.userId,
      rating,
      comment,
      photos: photos || [],
      submittedAt: new Date()
    });

    await activity.save();

    res.json({
      message: 'Feedback submitted successfully',
      averageRating: activity.getAverageRating()
    });
  } catch (error) {
    console.error('Submit Feedback Error:', error);
    res.status(500).json({ error: 'Failed to submit feedback' });
  }
};

/**
 * 获取推荐活动
 */
export const getRecommendedActivities = async (req, res) => {
  try {
    const user = req.user;
    const limit = parseInt(req.query.limit) || 10;

    // 基于用户兴趣和偏好推荐
    const recommendedTypes = [];

    // 映射兴趣到活动类型
    const interestToActivityMap = {
      art: ['museum', 'art-gallery'],
      music: ['concert', 'karaoke'],
      sports: ['sports', 'hiking'],
      gaming: ['escape-room', 'board-games'],
      food: ['cafe-hopping', 'cooking-class', 'wine-tasting'],
      photography: ['photography-walk', 'art-gallery'],
      outdoor: ['camping', 'hiking', 'photography-walk']
    };

    user.interests?.forEach(interest => {
      const mappedActivities = interestToActivityMap[interest];
      if (mappedActivities) {
        recommendedTypes.push(...mappedActivities);
      }
    });

    // 添加用户偏好的活动
    if (user.activityPreferences?.preferredActivities) {
      recommendedTypes.push(...user.activityPreferences.preferredActivities);
    }

    const query = {
      status: 'published',
      'schedule.startTime': { $gte: new Date() },
      type: { $in: [...new Set(recommendedTypes)] } // 去重
    };

    // 添加位置过滤
    if (user.profile?.location?.city) {
      query['location.city'] = user.profile.location.city;
    }

    const activities = await Activity.find(query)
      .populate('organizer', 'username profile.displayName')
      .sort({ 'schedule.startTime': 1 })
      .limit(limit);

    res.json({
      activities,
      recommendations: activities.length,
      basedOn: {
        interests: user.interests,
        preferences: user.activityPreferences?.preferredActivities
      }
    });
  } catch (error) {
    console.error('Get Recommended Activities Error:', error);
    res.status(500).json({ error: 'Failed to get recommended activities' });
  }
};
