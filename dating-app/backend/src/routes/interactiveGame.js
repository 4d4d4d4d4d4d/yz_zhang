import express from 'express';
import { authenticate } from '../middleware/auth.js';
import {
  createInteractiveGame,
  getPublicGames,
  joinGame,
  startGame,
  submitDrawing,
  submitGuess,
  sendGameChat,
  getGameDetails,
  getScriptTemplates
} from '../controllers/interactiveGameController.js';

const router = express.Router();

// Game management
router.post('/', authenticate, createInteractiveGame);
router.get('/public', authenticate, getPublicGames);
router.get('/templates/scripts', authenticate, getScriptTemplates);
router.get('/:gameId', authenticate, getGameDetails);
router.post('/:gameId/join', authenticate, joinGame);
router.post('/:gameId/start', authenticate, startGame);

// Game actions
router.post('/:gameId/drawing', authenticate, submitDrawing);
router.post('/:gameId/guess', authenticate, submitGuess);
router.post('/:gameId/chat', authenticate, sendGameChat);

export default router;
