// 游戏问题库
export const gameQuestions = {
  // 真心话问题
  truthQuestions: [
    '你最尴尬的约会经历是什么？',
    '你理想中的另一半是什么样的？',
    '你做过最疯狂的事情是什么？',
    '你暗恋过谁？持续了多久？',
    '你最后悔的一件事是什么？',
    '如果可以改变一件事，你会改变什么？',
    '你最大的秘密是什么？',
    '你对现在的生活满意吗？',
    '你最想去的地方是哪里？',
    '你相信一见钟情吗？',
    '你会为爱情放弃什么？',
    '你最欣赏自己的哪一点？',
    '你觉得自己最大的缺点是什么？',
    '你做过最浪漫的事是什么？',
    '你对前任还有感觉吗？'
  ],

  // 大冒险任务
  dareQuestions: [
    '发一条朋友圈夸夸对方',
    '用最温柔的声音说"我喜欢你"',
    '分享一张你最丑的照片',
    '模仿一个动物叫声',
    '说一个冷笑话',
    '唱一首歌',
    '跳一段舞',
    '做10个俯卧撑',
    '给对方发一个表白短信（可以说是游戏）',
    '分享你手机里最后一张照片',
    '用一个词形容对方',
    '说出对方的三个优点',
    '讲一个尴尬的故事',
    '模仿对方的一个习惯动作',
    '闭眼30秒，说出你想到的事'
  ],

  // 宁愿选择题
  wouldYouRatherQuestions: [
    {
      question: '你更愿意...',
      optionA: '永远单身但有很多朋友',
      optionB: '找到真爱但失去所有朋友'
    },
    {
      question: '你更愿意...',
      optionA: '能读懂别人的心思',
      optionB: '能让别人读懂你的心思'
    },
    {
      question: '你更愿意...',
      optionA: '每天旅行但住帐篷',
      optionB: '待在豪宅但不能出门'
    },
    {
      question: '你更愿意...',
      optionA: '有用不完的钱但很孤独',
      optionB: '很穷但有真爱'
    },
    {
      question: '约会时，你更愿意...',
      optionA: '去冒险刺激的地方',
      optionB: '去安静浪漫的地方'
    },
    {
      question: '你更愿意...',
      optionA: '知道自己何时死亡',
      optionB: '知道自己如何死亡'
    },
    {
      question: '你更愿意...',
      optionA: '永远25岁的外表',
      optionB: '永远25岁的心态'
    },
    {
      question: '你更愿意...',
      optionA: '能时间旅行到过去',
      optionB: '能时间旅行到未来'
    },
    {
      question: '在感情中，你更愿意...',
      optionA: '先说"我爱你"',
      optionB: '先听到"我爱你"'
    },
    {
      question: '你更愿意...',
      optionA: '有一个普通但体贴的伴侣',
      optionB: '有一个完美但忙碌的伴侣'
    }
  ],

  // 性格测试题
  personalityQuestions: [
    {
      question: '在社交场合中，你通常...',
      options: [
        { text: '主动和陌生人交谈', trait: 'extrovert', value: 5 },
        { text: '等别人先开口', trait: 'introvert', value: 5 },
        { text: '只和熟人交流', trait: 'introvert', value: 3 },
        { text: '观察环境再决定', trait: 'balanced', value: 3 }
      ]
    },
    {
      question: '做决定时，你更依赖...',
      options: [
        { text: '直觉和感受', trait: 'emotional', value: 5 },
        { text: '逻辑和数据', trait: 'rational', value: 5 },
        { text: '他人的建议', trait: 'social', value: 3 },
        { text: '过往经验', trait: 'practical', value: 4 }
      ]
    },
    {
      question: '面对冲突时，你会...',
      options: [
        { text: '直接表达不满', trait: 'assertive', value: 5 },
        { text: '避免正面冲突', trait: 'peaceful', value: 5 },
        { text: '寻求妥协方案', trait: 'diplomatic', value: 4 },
        { text: '需要时间冷静', trait: 'thoughtful', value: 4 }
      ]
    },
    {
      question: '理想的周末是...',
      options: [
        { text: '户外探险', trait: 'adventurous', value: 5 },
        { text: '在家放松', trait: 'homebody', value: 5 },
        { text: '和朋友聚会', trait: 'social', value: 4 },
        { text: '学习新技能', trait: 'curious', value: 4 }
      ]
    },
    {
      question: '在感情中，你更看重...',
      options: [
        { text: '深度的情感连接', trait: 'emotional', value: 5 },
        { text: '共同的兴趣爱好', trait: 'compatible', value: 4 },
        { text: '稳定和安全感', trait: 'stable', value: 4 },
        { text: '激情和浪漫', trait: 'romantic', value: 5 }
      ]
    },
    {
      question: '压力大时，你倾向于...',
      options: [
        { text: '找朋友倾诉', trait: 'social', value: 5 },
        { text: '独自消化', trait: 'independent', value: 5 },
        { text: '运动发泄', trait: 'active', value: 4 },
        { text: '睡觉休息', trait: 'relaxed', value: 3 }
      ]
    },
    {
      question: '对于未来，你...',
      options: [
        { text: '有详细计划', trait: 'organized', value: 5 },
        { text: '随遇而安', trait: 'spontaneous', value: 5 },
        { text: '有大致方向', trait: 'balanced', value: 4 },
        { text: '充满担忧', trait: 'anxious', value: 3 }
      ]
    },
    {
      question: '收到礼物时，你更在意...',
      options: [
        { text: '礼物的实用性', trait: 'practical', value: 5 },
        { text: '送礼人的心意', trait: 'emotional', value: 5 },
        { text: '礼物的价值', trait: 'materialistic', value: 3 },
        { text: '礼物的创意', trait: 'creative', value: 4 }
      ]
    }
  ],

  // 破冰卡片问题
  iceBreakerQuestions: [
    '如果能拥有一个超能力，你会选什么？',
    '你最喜欢的电影/书籍是什么？为什么？',
    '描述你理想中的一天',
    '你最想学习的技能是什么？',
    '童年最美好的回忆是什么？',
    '如果可以和任何人共进晚餐（活着或已故），你会选谁？',
    '你最自豪的成就是什么？',
    '如果中了彩票，你会做什么？',
    '你觉得什么样的人最有魅力？',
    '你最想去体验的事情是什么？',
    '描述你的梦想职业',
    '你最珍惜的物品是什么？',
    '如果能回到过去，你想对年轻的自己说什么？',
    '你认为友情/爱情最重要的是什么？',
    '你最喜欢的季节是什么？为什么？'
  ]
};

// 获取随机问题
export const getRandomQuestion = (type, difficulty = 'medium') => {
  let questions;

  switch (type) {
    case 'truth':
      questions = gameQuestions.truthQuestions;
      break;
    case 'dare':
      questions = gameQuestions.dareQuestions;
      break;
    case 'would-you-rather':
      questions = gameQuestions.wouldYouRatherQuestions;
      break;
    case 'ice-breaker':
      questions = gameQuestions.iceBreakerQuestions;
      break;
    default:
      questions = gameQuestions.iceBreakerQuestions;
  }

  const randomIndex = Math.floor(Math.random() * questions.length);
  return questions[randomIndex];
};

// 分析性格测试结果
export const analyzePersonalityTest = (answers) => {
  const traits = {};

  // 计算各个特质的分数
  answers.forEach(answer => {
    if (answer.trait) {
      traits[answer.trait] = (traits[answer.trait] || 0) + answer.value;
    }
  });

  // 找出主导特质
  const sortedTraits = Object.entries(traits)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3);

  // 生成性格描述
  const personalityTypes = {
    extrovert: '外向型 - 你喜欢社交，从人群中获得能量',
    introvert: '内向型 - 你享受独处，需要时间充电',
    emotional: '感性型 - 你重视情感，凭感觉做决定',
    rational: '理性型 - 你逻辑清晰，依靠分析思考',
    adventurous: '冒险型 - 你勇于尝试新事物，热爱挑战',
    stable: '稳定型 - 你追求安全感，喜欢可预测的生活',
    social: '社交型 - 你重视人际关系，善于沟通',
    independent: '独立型 - 你自给自足，喜欢掌控生活',
    romantic: '浪漫型 - 你富有想象力，追求诗意生活',
    practical: '务实型 - 你脚踏实地，注重实际'
  };

  const topTraits = sortedTraits.map(([trait]) => trait);
  const description = topTraits
    .map(trait => personalityTypes[trait])
    .filter(Boolean)
    .join('；');

  return {
    type: topTraits[0] || 'balanced',
    traits: topTraits,
    description: description || '你是一个平衡的人，各方面都很均衡',
    scores: traits
  };
};

// 计算游戏兼容性
export const calculateGameCompatibility = (user1Result, user2Result) => {
  const traits1 = new Set(user1Result.traits);
  const traits2 = new Set(user2Result.traits);

  // 互补性特质
  const complementary = {
    extrovert: 'introvert',
    introvert: 'extrovert',
    emotional: 'rational',
    rational: 'emotional',
    adventurous: 'stable',
    stable: 'adventurous'
  };

  let score = 50; // 基础分

  // 共同特质加分
  const commonTraits = [...traits1].filter(t => traits2.has(t));
  score += commonTraits.length * 10;

  // 互补特质加分
  traits1.forEach(trait => {
    if (traits2.has(complementary[trait])) {
      score += 15;
    }
  });

  return Math.min(100, score);
};

export default {
  gameQuestions,
  getRandomQuestion,
  analyzePersonalityTest,
  calculateGameCompatibility
};
