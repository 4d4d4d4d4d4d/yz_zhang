import express from 'express';
import { authenticate } from '../middleware/auth.js';
import {
  createMoment,
  getMomentsFeed,
  getUserMoments,
  getMomentById,
  toggleLike,
  addComment,
  deleteComment,
  voteOnPoll,
  deleteMoment,
  getTrendingTopics,
  getNearbyMoments
} from '../controllers/momentController.js';

const router = express.Router();

// Moment CRUD
router.post('/', authenticate, createMoment);
router.get('/feed', authenticate, getMomentsFeed);
router.get('/trending', authenticate, getTrendingTopics);
router.get('/nearby', authenticate, getNearbyMoments);
router.get('/user/:userId', authenticate, getUserMoments);
router.get('/:momentId', authenticate, getMomentById);
router.delete('/:momentId', authenticate, deleteMoment);

// Interactions
router.post('/:momentId/like', authenticate, toggleLike);
router.post('/:momentId/comment', authenticate, addComment);
router.delete('/:momentId/comment/:commentId', authenticate, deleteComment);
router.post('/:momentId/vote', authenticate, voteOnPoll);

export default router;
