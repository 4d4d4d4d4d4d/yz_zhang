import express from 'express';
import {
  companionChat,
  getDatingAdvice,
  analyzeEmotion,
  getAIConversations,
  generateIceBreakers,
  getConversationTips
} from '../controllers/aiController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有AI路由都需要认证
router.use(authenticate);

// AI伴侣聊天
router.post('/companion/chat', companionChat);

// 约会教练
router.post('/dating-coach/advice', getDatingAdvice);

// 情绪分析
router.post('/emotion/analyze', analyzeEmotion);

// 获取AI对话历史
router.get('/conversations', getAIConversations);

// 生成破冰话题
router.get('/ice-breakers', generateIceBreakers);

// 获取对话建议
router.get('/conversation-tips', getConversationTips);

export default router;
