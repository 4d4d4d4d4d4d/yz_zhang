import express from 'express';
import { authenticate } from '../middleware/auth.js';
import {
  blockUser,
  unblockUser,
  getBlockedUsers,
  checkBlocked,
  reportUser,
  getMyReports,
  cancelReport
} from '../controllers/safetyController.js';

const router = express.Router();

// Block routes
router.post('/block/:userId', authenticate, blockUser);
router.delete('/block/:userId', authenticate, unblockUser);
router.get('/blocked', authenticate, getBlockedUsers);
router.get('/blocked/:userId', authenticate, checkBlocked);

// Report routes
router.post('/report/:userId', authenticate, reportUser);
router.get('/reports', authenticate, getMyReports);
router.delete('/reports/:reportId', authenticate, cancelReport);

export default router;
