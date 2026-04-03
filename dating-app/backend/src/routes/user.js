import express from 'express';
import {
  searchUsers,
  getRecommendedUsers,
  getUserProfile,
  getOnlineUsers,
  getNearbyUsers,
  getPopularUsers
} from '../controllers/userController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有用户路由都需要认证
router.use(authenticate);

// 搜索用户
router.get('/search', searchUsers);

// 获取推荐用户
router.get('/recommended', getRecommendedUsers);

// 获取在线用户
router.get('/online', getOnlineUsers);

// 获取附近用户
router.get('/nearby', getNearbyUsers);

// 获取热门用户
router.get('/popular', getPopularUsers);

// 获取用户详情
router.get('/:userId', getUserProfile);

export default router;
