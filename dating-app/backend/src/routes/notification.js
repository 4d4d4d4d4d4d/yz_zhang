import express from 'express';
import {
  getMyNotifications,
  getUnreadCount,
  markAsRead,
  markAllAsRead,
  deleteNotification,
  clearReadNotifications
} from '../controllers/notificationController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有通知路由都需要认证
router.use(authenticate);

// 获取通知列表
router.get('/', getMyNotifications);

// 获取未读数量
router.get('/unread-count', getUnreadCount);

// 标记所有为已读
router.post('/mark-all-read', markAllAsRead);

// 清空已读通知
router.delete('/clear-read', clearReadNotifications);

// 标记单个为已读
router.patch('/:notificationId/read', markAsRead);

// 删除单个通知
router.delete('/:notificationId', deleteNotification);

export default router;
