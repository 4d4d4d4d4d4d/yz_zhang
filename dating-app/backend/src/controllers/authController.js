import User from '../models/User.js';
import { generateToken } from '../middleware/auth.js';
import aiService from '../services/aiService.js';

export const register = async (req, res) => {
  try {
    const { username, email, password, profile, interests, aiAvatar } = req.body;

    // 检查用户是否已存在
    const existingUser = await User.findOne({ $or: [{ email }, { username }] });
    if (existingUser) {
      return res.status(400).json({
        error: existingUser.email === email ? 'Email already exists' : 'Username already exists'
      });
    }

    // 生成AI化身描述
    const avatarPersona = await aiService.generateAvatarPersona({
      interests,
      aiAvatar,
      emotionalState: { current: 'calm' }
    });

    // 创建新用户
    const user = new User({
      username,
      email,
      password,
      profile: {
        ...profile,
        bio: avatarPersona
      },
      interests,
      aiAvatar: {
        ...aiAvatar,
        personality: aiAvatar?.personality || 'mysterious'
      }
    });

    await user.save();

    // 生成token
    const token = generateToken(user._id);

    res.status(201).json({
      message: 'Registration successful',
      token,
      user: user.toPublicJSON()
    });
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Registration failed' });
  }
};

export const login = async (req, res) => {
  try {
    const { email, password } = req.body;

    // 查找用户
    const user = await User.findOne({ email });
    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // 验证密码
    const isMatch = await user.comparePassword(password);
    if (!isMatch) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // 检查账户状态
    if (!user.isActive) {
      return res.status(403).json({ error: 'Account is inactive' });
    }

    // 更新最后活跃时间
    user.lastActive = new Date();
    await user.save();

    // 生成token
    const token = generateToken(user._id);

    res.json({
      message: 'Login successful',
      token,
      user: user.toPublicJSON()
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
};

export const getProfile = async (req, res) => {
  try {
    res.json({
      user: req.user.toPublicJSON()
    });
  } catch (error) {
    console.error('Get profile error:', error);
    res.status(500).json({ error: 'Failed to get profile' });
  }
};

export const updateProfile = async (req, res) => {
  try {
    const updates = req.body;
    const allowedUpdates = [
      'profile', 'interests', 'talents', 'emotionalState',
      'activityPreferences', 'matchPreferences', 'aiAvatar'
    ];

    const user = req.user;

    // 更新允许的字段
    Object.keys(updates).forEach(key => {
      if (allowedUpdates.includes(key)) {
        if (typeof updates[key] === 'object' && !Array.isArray(updates[key])) {
          user[key] = { ...user[key], ...updates[key] };
        } else {
          user[key] = updates[key];
        }
      }
    });

    // 如果更新了兴趣或AI化身，重新生成描述
    if (updates.interests || updates.aiAvatar) {
      const avatarPersona = await aiService.generateAvatarPersona({
        interests: user.interests,
        aiAvatar: user.aiAvatar,
        emotionalState: user.emotionalState
      });
      user.profile.bio = avatarPersona;
    }

    await user.save();

    res.json({
      message: 'Profile updated successfully',
      user: user.toPublicJSON()
    });
  } catch (error) {
    console.error('Update profile error:', error);
    res.status(500).json({ error: 'Failed to update profile' });
  }
};
