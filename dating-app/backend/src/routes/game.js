import express from 'express';
import {
  createGame,
  joinGame,
  startGame,
  getGameDetails,
  getQuestion,
  submitAnswer,
  getPersonalityTest,
  submitPersonalityTest,
  endGame,
  getUserGames,
  getPublicGames,
  rateGame
} from '../controllers/gameController.js';
import { authenticate } from '../middleware/auth.js';

const router = express.Router();

// 所有游戏路由都需要认证
router.use(authenticate);

// 游戏管理
router.post('/', createGame);
router.get('/public', getPublicGames);
router.get('/my-games', getUserGames);

// 性格测试
router.get('/personality-test/questions', getPersonalityTest);

// 游戏操作
router.get('/:gameId', getGameDetails);
router.post('/:gameId/join', joinGame);
router.post('/:gameId/start', startGame);
router.get('/:gameId/question', getQuestion);
router.post('/:gameId/answer', submitAnswer);
router.post('/:gameId/personality-test', submitPersonalityTest);
router.post('/:gameId/end', endGame);
router.post('/:gameId/rate', rateGame);

export default router;
