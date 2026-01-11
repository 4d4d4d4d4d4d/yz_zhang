import express from 'express';
import {
  getActivities,
  createActivity,
  getActivityDetails,
  joinActivity,
  leaveActivity,
  getRandomActivity,
  submitFeedback,
  getRecommendedActivities
} from '../controllers/activityController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有活动路由都需要认证
router.use(authenticate);

// 获取活动列表
router.get('/', getActivities);

// 创建活动
router.post('/', createActivity);

// 获取推荐活动
router.get('/recommendations', getRecommendedActivities);

// 随机匹配活动
router.get('/random', getRandomActivity);

// 获取活动详情
router.get('/:activityId', getActivityDetails);

// 报名参加活动
router.post('/:activityId/join', joinActivity);

// 取消报名
router.post('/:activityId/leave', leaveActivity);

// 提交活动反馈
router.post('/:activityId/feedback', submitFeedback);

export default router;
