import InteractiveGame from '../models/InteractiveGame.js';
import User from '../models/User.js';

// Script murder themes and templates
const scriptMurderTemplates = {
  'mystery_manor': {
    theme: 'mystery',
    title: '神秘庄园谋杀案',
    description: '在一座与世隔绝的庄园中，发生了一起离奇的谋杀案...',
    difficulty: 'medium',
    roles: [
      { name: '庄园主', description: '庄园的拥有者，神秘而富有' },
      { name: '管家', description: '忠诚的仆人，知晓许多秘密' },
      { name: '侦探', description: '受邀而来的名侦探' },
      { name: '继承人', description: '庄园主的侄子，急需财产' },
      { name: '医生', description: '家庭医生，了解所有人的健康状况' },
      { name: '记者', description: '来采访的记者，善于发现蛛丝马迹' }
    ]
  },
  'campus_mystery': {
    theme: 'mystery',
    title: '校园迷案',
    description: '深夜的图书馆，一桩神秘事件正在发生...',
    difficulty: 'easy',
    roles: [
      { name: '学霸', description: '成绩优异的学生' },
      { name: '社团长', description: '活跃的社团负责人' },
      { name: '老师', description: '关心学生的班主任' },
      { name: '校霸', description: '校园里的风云人物' }
    ]
  }
};

// Draw & Guess word lists
const drawGuessWords = {
  animals: ['猫', '狗', '大象', '长颈鹿', '熊猫', '企鹅', '鲸鱼', '蝴蝶'],
  objects: ['雨伞', '眼镜', '钥匙', '手机', '自行车', '钢琴', '火箭', '城堡'],
  food: ['汉堡', '比萨', '寿司', '冰淇淋', '西瓜', '葡萄', '蛋糕', '咖啡'],
  actions: ['跑步', '游泳', '跳舞', '唱歌', '睡觉', '读书', '画画', '做饭'],
  emotions: ['开心', '伤心', '生气', '惊讶', '害怕', '兴奋', '困惑', '平静']
};

// Create game
export const createInteractiveGame = async (req, res) => {
  try {
    const { gameType, title, description, maxParticipants, settings, scriptTheme } = req.body;

    const gameData = {
      gameType,
      title: title || getDefaultTitle(gameType),
      description,
      host: req.userId,
      maxParticipants: maxParticipants || getDefaultMaxParticipants(gameType),
      minParticipants: getMinParticipants(gameType),
      settings: settings || {},
      participants: [{ user: req.userId, role: 'host' }]
    };

    // Initialize game-specific data
    if (gameType === 'script_murder' && scriptTheme) {
      const template = scriptMurderTemplates[scriptTheme];
      if (template) {
        gameData.scriptData = {
          scriptId: scriptTheme,
          theme: template.theme,
          difficulty: template.difficulty,
          roles: template.roles.map(r => ({ ...r, assignedTo: null })),
          plot: template.description,
          clues: []
        };
      }
    } else if (gameType === 'draw_guess') {
      gameData.drawGuessData = {
        rounds: [],
        wordList: generateWordList(),
        currentRound: 0
      };
    } else if (gameType === 'werewolf') {
      gameData.werewolfData = {
        phase: 'waiting',
        dayCount: 0,
        roles: [],
        events: [],
        votes: []
      };
    }

    const game = new InteractiveGame(gameData);
    await game.save();

    await game.populate('host', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '游戏创建成功', game });
  } catch (error) {
    console.error('Create interactive game error:', error);
    res.status(500).json({ error: '创建游戏失败' });
  }
};

// Get public games
export const getPublicGames = async (req, res) => {
  try {
    const { gameType, status = 'waiting', page = 1, limit = 20 } = req.query;
    const skip = (page - 1) * limit;

    const query = {
      'settings.isPrivate': false,
      status
    };

    if (gameType) {
      query.gameType = gameType;
    }

    const games = await InteractiveGame.find(query)
      .populate('host', 'username profile.displayName profile.aiAvatar')
      .populate('participants.user', 'username profile.displayName profile.aiAvatar')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit));

    const total = await InteractiveGame.countDocuments(query);

    res.json({
      games,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get public games error:', error);
    res.status(500).json({ error: '获取游戏列表失败' });
  }
};

// Join game
export const joinGame = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { password } = req.body;

    const game = await InteractiveGame.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: '游戏不存在' });
    }

    if (game.status !== 'waiting') {
      return res.status(400).json({ error: '游戏已开始或已结束' });
    }

    if (game.settings.password && game.settings.password !== password) {
      return res.status(401).json({ error: '密码错误' });
    }

    game.addParticipant(req.userId);
    await game.save();

    await game.populate('participants.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '加入游戏成功', game });
  } catch (error) {
    console.error('Join game error:', error);
    res.status(400).json({ error: error.message || '加入游戏失败' });
  }
};

// Start game
export const startGame = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await InteractiveGame.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: '游戏不存在' });
    }

    if (game.host.toString() !== req.userId) {
      return res.status(403).json({ error: '只有房主可以开始游戏' });
    }

    if (!game.canStart()) {
      return res.status(400).json({ error: `需要${game.minParticipants}-${game.maxParticipants}名玩家` });
    }

    // Initialize game based on type
    if (game.gameType === 'script_murder') {
      assignScriptRoles(game);
    } else if (game.gameType === 'werewolf') {
      assignWerewolfRoles(game);
    } else if (game.gameType === 'draw_guess') {
      initializeDrawGuess(game);
    }

    game.status = 'started';
    game.startedAt = new Date();
    await game.save();

    await game.populate('participants.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '游戏开始', game });
  } catch (error) {
    console.error('Start game error:', error);
    res.status(500).json({ error: '开始游戏失败' });
  }
};

// Submit drawing
export const submitDrawing = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { drawing } = req.body;

    const game = await InteractiveGame.findById(gameId);
    if (!game || game.gameType !== 'draw_guess') {
      return res.status(404).json({ error: '游戏不存在' });
    }

    const currentRound = game.drawGuessData.rounds[game.drawGuessData.currentRound];
    if (!currentRound || currentRound.drawer.toString() !== req.userId) {
      return res.status(403).json({ error: '不是当前绘画者' });
    }

    currentRound.drawing = drawing;
    await game.save();

    res.json({ message: '绘画已提交', round: currentRound });
  } catch (error) {
    console.error('Submit drawing error:', error);
    res.status(500).json({ error: '提交绘画失败' });
  }
};

// Submit guess
export const submitGuess = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { guess } = req.body;

    const game = await InteractiveGame.findById(gameId);
    if (!game || game.gameType !== 'draw_guess') {
      return res.status(404).json({ error: '游戏不存在' });
    }

    const currentRound = game.drawGuessData.rounds[game.drawGuessData.currentRound];
    if (!currentRound) {
      return res.status(400).json({ error: '当前没有进行中的回合' });
    }

    if (currentRound.drawer.toString() === req.userId) {
      return res.status(400).json({ error: '绘画者不能猜答案' });
    }

    const correct = guess.toLowerCase() === currentRound.word.toLowerCase();

    currentRound.guesses.push({
      user: req.userId,
      guess,
      timestamp: new Date(),
      correct
    });

    // Award points
    if (correct) {
      const participant = game.participants.find(p => p.user.toString() === req.userId);
      if (participant) {
        const timeBonus = Math.max(0, 60 - currentRound.guesses.length * 5);
        participant.score += 100 + timeBonus;
      }

      // Drawer also gets points
      const drawer = game.participants.find(p => p.user.toString() === currentRound.drawer.toString());
      if (drawer) {
        drawer.score += 50;
      }

      // Move to next round or end game
      if (game.drawGuessData.currentRound + 1 >= game.participants.length) {
        game.status = 'completed';
        game.completedAt = new Date();
        calculateResults(game);
      } else {
        currentRound.completedAt = new Date();
        game.drawGuessData.currentRound += 1;
        startNewDrawGuessRound(game);
      }
    }

    await game.save();

    res.json({
      message: correct ? '回答正确！' : '继续猜',
      correct,
      game
    });
  } catch (error) {
    console.error('Submit guess error:', error);
    res.status(500).json({ error: '提交猜测失败' });
  }
};

// Send game chat
export const sendGameChat = async (req, res) => {
  try {
    const { gameId } = req.params;
    const { message, type = 'text' } = req.body;

    const game = await InteractiveGame.findById(gameId);
    if (!game) {
      return res.status(404).json({ error: '游戏不存在' });
    }

    const isParticipant = game.participants.some(p => p.user.toString() === req.userId);
    if (!isParticipant) {
      return res.status(403).json({ error: '只有参与者可以发送消息' });
    }

    game.chat.push({
      user: req.userId,
      message,
      type,
      timestamp: new Date()
    });

    await game.save();

    const chatMessage = game.chat[game.chat.length - 1];
    await game.populate('chat.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '消息已发送', chat: chatMessage });
  } catch (error) {
    console.error('Send game chat error:', error);
    res.status(500).json({ error: '发送消息失败' });
  }
};

// Helper functions
function getDefaultTitle(gameType) {
  const titles = {
    script_murder: '剧本杀房间',
    draw_guess: '你画我猜',
    werewolf: '狼人杀',
    mafia: '天黑请闭眼',
    truth_dare: '真心话大冒险',
    word_chain: '成语接龙',
    riddle: '谜语竞猜',
    karaoke: 'K歌房'
  };
  return titles[gameType] || '互动游戏';
}

function getDefaultMaxParticipants(gameType) {
  const maxes = {
    script_murder: 6,
    draw_guess: 8,
    werewolf: 12,
    mafia: 10,
    truth_dare: 10,
    word_chain: 6,
    riddle: 8,
    karaoke: 6
  };
  return maxes[gameType] || 8;
}

function getMinParticipants(gameType) {
  const mins = {
    script_murder: 4,
    draw_guess: 2,
    werewolf: 6,
    mafia: 6,
    truth_dare: 2,
    word_chain: 2,
    riddle: 2,
    karaoke: 2
  };
  return mins[gameType] || 2;
}

function generateWordList() {
  const allWords = Object.values(drawGuessWords).flat();
  return shuffleArray(allWords).slice(0, 20);
}

function shuffleArray(array) {
  const newArray = [...array];
  for (let i = newArray.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
  }
  return newArray;
}

function assignScriptRoles(game) {
  const roles = shuffleArray([...game.scriptData.roles]);
  game.participants.forEach((participant, index) => {
    if (index < roles.length) {
      participant.role = roles[index].name;
      roles[index].assignedTo = participant.user;
    }
  });

  // Randomly assign murderer
  const randomIndex = Math.floor(Math.random() * game.participants.length);
  game.scriptData.murderer = game.participants[randomIndex].user;
}

function assignWerewolfRoles(game) {
  const playerCount = game.participants.length;
  const werewolfCount = Math.floor(playerCount / 3);

  const rolePool = [];
  for (let i = 0; i < werewolfCount; i++) rolePool.push('werewolf');
  rolePool.push('seer', 'doctor');
  while (rolePool.length < playerCount) rolePool.push('villager');

  const shuffledRoles = shuffleArray(rolePool);

  game.werewolfData.roles = game.participants.map((p, index) => ({
    userId: p.user,
    role: shuffledRoles[index],
    alive: true
  }));

  game.werewolfData.phase = 'night';
  game.werewolfData.dayCount = 1;
}

function initializeDrawGuess(game) {
  startNewDrawGuessRound(game);
}

function startNewDrawGuessRound(game) {
  const roundNumber = game.drawGuessData.rounds.length;
  const drawerIndex = roundNumber % game.participants.length;
  const drawer = game.participants[drawerIndex].user;
  const word = game.drawGuessData.wordList[roundNumber % game.drawGuessData.wordList.length];

  game.drawGuessData.rounds.push({
    roundNumber,
    drawer,
    word,
    category: 'mixed',
    guesses: [],
    timeLimit: 60,
    startedAt: new Date()
  });
}

function calculateResults(game) {
  const sorted = [...game.participants].sort((a, b) => b.score - a.score);

  game.results = sorted.map((p, index) => ({
    user: p.user,
    score: p.score,
    rank: index + 1,
    achievements: index === 0 ? ['冠军'] : []
  }));

  if (sorted.length > 0) {
    game.winner = sorted[0].user;
  }
}

export const getGameDetails = async (req, res) => {
  try {
    const { gameId } = req.params;

    const game = await InteractiveGame.findById(gameId)
      .populate('host', 'username profile.displayName profile.aiAvatar')
      .populate('participants.user', 'username profile.displayName profile.aiAvatar')
      .populate('chat.user', 'username profile.displayName profile.aiAvatar');

    if (!game) {
      return res.status(404).json({ error: '游戏不存在' });
    }

    res.json({ game });
  } catch (error) {
    console.error('Get game details error:', error);
    res.status(500).json({ error: '获取游戏详情失败' });
  }
};

export const getScriptTemplates = async (req, res) => {
  try {
    res.json({ templates: scriptMurderTemplates });
  } catch (error) {
    console.error('Get script templates error:', error);
    res.status(500).json({ error: '获取剧本模板失败' });
  }
};
