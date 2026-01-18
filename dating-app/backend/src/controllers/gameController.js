import Game from '../models/Game.js';
import User from '../models/User.js';
import {
  getRandomQuestion,
  gameQuestions,
  analyzePersonalityTest,
  calculateGameCompatibility
} from '../services/gameService.js';

/**
 * 创建新游戏
 */
export const createGame = async (req, res) => {
  try {
    const { type, name, settings, inviteUserId } = req.body;

    const game = new Game({
      type,
      name: name || `${type}游戏`,
      createdBy: req.userId,
      settings: settings || {},
      participants: [{
        user: req.userId,
        joinedAt: new Date(),
        status: 'active'
      }]
    });

    // 如果邀请了其他用户
    if (inviteUserId) {
      game.addParticipant(inviteUserId);
    }

    await game.save();

    // 更新用户统计
    req.user.stats.gamesPlayed += 1;
    await req.user.save();

    res.status(201).json({
      message: 'Game created successfully',
      game
    });
  } catch (error) {
    console.error('Create Game Error:', error);
    res.status(500).json({ error: error.message || 'Failed to create game' });
  }
};

/**
 * 加入游戏
 */
export const joinGame = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    if (game.status !== 'waiting') {
      return res.status(400).json({ error: 'Game already started or completed' });
    }

    game.addParticipant(req.userId);
    await game.save();

    // 更新用户统计
    req.user.stats.gamesPlayed += 1;
    await req.user.save();

    res.json({
      message: 'Joined game successfully',
      game
    });
  } catch (error) {
    console.error('Join Game Error:', error);
    res.status(500).json({ error: error.message || 'Failed to join game' });
  }
};

/**
 * 开始游戏
 */
export const startGame = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await Game.findById(gameId)
      .populate('participants.user', 'username profile.displayName');

    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 检查是否是创建者
    if (game.createdBy.toString() !== req.userId.toString()) {
      return res.status(403).json({ error: 'Only creator can start the game' });
    }

    game.startGame();
    await game.save();

    res.json({
      message: 'Game started',
      game,
      firstQuestion: getRandomQuestion(game.type === 'truth-or-dare' ? 'truth' : 'ice-breaker')
    });
  } catch (error) {
    console.error('Start Game Error:', error);
    res.status(500).json({ error: error.message || 'Failed to start game' });
  }
};

/**
 * 获取游戏详情
 */
export const getGameDetails = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await Game.findById(gameId)
      .populate('participants.user', 'username profile aiAvatar')
      .populate('createdBy', 'username profile.displayName');

    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 检查用户是否是参与者
    const isParticipant = game.participants.some(
      p => p.user._id.toString() === req.userId.toString()
    );

    if (!isParticipant && !game.settings.allowSpectators) {
      return res.status(403).json({ error: 'Not a participant' });
    }

    res.json({ game });
  } catch (error) {
    console.error('Get Game Details Error:', error);
    res.status(500).json({ error: 'Failed to get game details' });
  }
};

/**
 * 获取新问题
 */
export const getQuestion = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { questionType } = req.query;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 检查是否轮到当前用户
    if (game.session.currentTurn?.toString() !== req.userId.toString()) {
      return res.status(403).json({ error: 'Not your turn' });
    }

    let question;
    let type = questionType;

    if (game.type === 'truth-or-dare') {
      type = questionType || (Math.random() > 0.5 ? 'truth' : 'dare');
    } else if (game.type === 'would-you-rather') {
      type = 'would-you-rather';
    } else if (game.type === 'ice-breaker-cards') {
      type = 'ice-breaker';
    }

    question = getRandomQuestion(type);

    // 添加到游戏记录
    const questionId = Date.now().toString();
    game.addQuestion({
      questionId,
      question: typeof question === 'string' ? question : question.question,
      type,
      askedBy: req.userId,
      answeredBy: game.participants.find(
        p => p.user.toString() !== req.userId.toString()
      )?.user
    });

    await game.save();

    res.json({
      question,
      questionId,
      type,
      round: game.session.currentRound
    });
  } catch (error) {
    console.error('Get Question Error:', error);
    res.status(500).json({ error: 'Failed to get question' });
  }
};

/**
 * 提交答案
 */
export const submitAnswer = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { questionId, answer } = req.body;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    game.recordAnswer(questionId, answer);
    game.nextTurn();

    await game.save();

    res.json({
      message: 'Answer recorded',
      nextTurn: game.session.currentTurn,
      round: game.session.currentRound
    });
  } catch (error) {
    console.error('Submit Answer Error:', error);
    res.status(500).json({ error: 'Failed to submit answer' });
  }
};

/**
 * 性格测试 - 获取题目
 */
export const getPersonalityTest = async (req, res) => {
  try {
    res.json({
      questions: gameQuestions.personalityQuestions,
      totalQuestions: gameQuestions.personalityQuestions.length
    });
  } catch (error) {
    console.error('Get Personality Test Error:', error);
    res.status(500).json({ error: 'Failed to get personality test' });
  }
};

/**
 * 性格测试 - 提交答案
 */
export const submitPersonalityTest = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { answers } = req.body;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 分析结果
    const result = analyzePersonalityTest(answers);

    // 保存结果
    game.personalityResults.push({
      user: req.userId,
      answers,
      result,
      completedAt: new Date()
    });

    await game.save();

    // 如果双方都完成了，计算兼容性
    let compatibility = null;
    if (game.personalityResults.length === 2) {
      const [result1, result2] = game.personalityResults;
      compatibility = calculateGameCompatibility(result1.result, result2.result);

      game.status = 'completed';
      game.completedAt = new Date();
      await game.save();
    }

    res.json({
      message: 'Test completed',
      result,
      compatibility
    });
  } catch (error) {
    console.error('Submit Personality Test Error:', error);
    res.status(500).json({ error: 'Failed to submit test' });
  }
};

/**
 * 结束游戏
 */
export const endGame = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 检查是否是参与者
    const isParticipant = game.participants.some(
      p => p.user.toString() === req.userId.toString()
    );

    if (!isParticipant) {
      return res.status(403).json({ error: 'Not a participant' });
    }

    game.finishGame();
    await game.save();

    res.json({
      message: 'Game ended',
      game
    });
  } catch (error) {
    console.error('End Game Error:', error);
    res.status(500).json({ error: 'Failed to end game' });
  }
};

/**
 * 获取用户的游戏历史
 */
export const getUserGames = async (req, res) => {
  try {
    const { status } = req.query;

    const query = {
      'participants.user': req.userId
    };

    if (status) {
      query.status = status;
    }

    const games = await Game.find(query)
      .populate('participants.user', 'username profile.displayName aiAvatar')
      .populate('createdBy', 'username profile.displayName')
      .sort({ createdAt: -1 })
      .limit(20);

    res.json({ games });
  } catch (error) {
    console.error('Get User Games Error:', error);
    res.status(500).json({ error: 'Failed to get games' });
  }
};

/**
 * 获取游戏列表（公开游戏）
 */
export const getPublicGames = async (req, res) => {
  try {
    const { type, status = 'waiting' } = req.query;

    const query = {
      'settings.isPrivate': false,
      status
    };

    if (type) {
      query.type = type;
    }

    const games = await Game.find(query)
      .populate('participants.user', 'username profile.displayName')
      .populate('createdBy', 'username profile.displayName')
      .sort({ createdAt: -1 })
      .limit(50);

    res.json({ games });
  } catch (error) {
    console.error('Get Public Games Error:', error);
    res.status(500).json({ error: 'Failed to get games' });
  }
};

/**
 * 评价游戏
 */
export const rateGame = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { rating } = req.body;

    const game = await Game.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: 'Game not found' });
    }

    // 检查是否是参与者
    const isParticipant = game.participants.some(
      p => p.user.toString() === req.userId.toString()
    );

    if (!isParticipant) {
      return res.status(403).json({ error: 'Not a participant' });
    }

    game.stats.funRating = rating;
    await game.save();

    res.json({
      message: 'Rating submitted',
      rating: game.stats.funRating
    });
  } catch (error) {
    console.error('Rate Game Error:', error);
    res.status(500).json({ error: 'Failed to rate game' });
  }
};
