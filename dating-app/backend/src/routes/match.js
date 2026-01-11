import express from 'express';
import {
  getRecommendations,
  createMatch,
  respondToMatch,
  getMyMatches,
  revealMysteryInfo,
  getMatchDetails
} from '../controllers/matchController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有匹配路由都需要认证
router.use(authenticate);

// 获取推荐匹配
router.get('/recommendations', getRecommendations);

// 创建匹配
router.post('/', createMatch);

// 获取我的匹配列表
router.get('/my-matches', getMyMatches);

// 获取匹配详情
router.get('/:matchId', getMatchDetails);

// 响应匹配请求
router.post('/:matchId/respond', respondToMatch);

// 解锁神秘信息
router.post('/:matchId/reveal', revealMysteryInfo);

export default router;
