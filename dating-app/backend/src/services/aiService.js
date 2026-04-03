import Anthropic from '@anthropic-ai/sdk';

class AIService {
  constructor() {
    this.client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY
    });
  }

  /**
   * AI伴侣聊天 - 提供情感支持和陪伴
   */
  async companionChat(userMessage, userContext = {}) {
    const { personality = 'warm', emotionalState = 'calm', conversationHistory = [] } = userContext;

    const systemPrompt = this.buildCompanionPrompt(personality, emotionalState);

    try {
      const message = await this.client.messages.create({
        model: 'claude-3-5-sonnet-20241022',
        max_tokens: 1024,
        system: systemPrompt,
        messages: [
          ...conversationHistory.slice(-10), // 保留最近10条消息作为上下文
          {
            role: 'user',
            content: userMessage
          }
        ]
      });

      const aiResponse = message.content[0].text;
      const emotion = this.detectEmotion(userMessage);
      const sentiment = this.analyzeSentiment(userMessage);

      return {
        response: aiResponse,
        emotion,
        sentiment,
        suggestions: this.generateSuggestions(userMessage, emotion)
      };
    } catch (error) {
      console.error('AI Companion Error:', error);
      throw new Error('AI companion service unavailable');
    }
  }

  /**
   * 约会教练 - 提供聊天技巧和建议
   */
  async datingCoach(scenario, userProfile) {
    const systemPrompt = `你是一位专业的约会教练，擅长提供真诚、实用的交友建议。

你的角色：
- 帮助用户改善沟通技巧
- 提供破冰话题建议
- 分析对话质量
- 给予情感支持

风格特点：
- 温暖友善但专业
- 给出具体可行的建议
- 鼓励真诚而非套路
- 注重双方感受

用户资料：
兴趣：${userProfile.interests?.join(', ') || '未设置'}
年龄：${userProfile.age || '未设置'}
性格：${userProfile.aiAvatar?.personality || 'mysterious'}`;

    try {
      const message = await this.client.messages.create({
        model: 'claude-3-5-sonnet-20241022',
        max_tokens: 1024,
        system: systemPrompt,
        messages: [{
          role: 'user',
          content: scenario
        }]
      });

      return {
        advice: message.content[0].text,
        iceBreakers: this.generateIceBreakers(userProfile),
        conversationTips: this.generateConversationTips()
      };
    } catch (error) {
      console.error('Dating Coach Error:', error);
      throw new Error('Dating coach service unavailable');
    }
  }

  /**
   * 情绪分析
   */
  async analyzeEmotion(text) {
    const emotion = this.detectEmotion(text);
    const sentiment = this.analyzeSentiment(text);

    return {
      emotion,
      sentiment,
      confidence: 0.85,
      suggestions: this.generateEmotionalSupport(emotion)
    };
  }

  /**
   * 匹配分析 - 评估两个用户的兼容性
   */
  async analyzeCompatibility(user1, user2) {
    // 兴趣匹配度
    const interestsScore = this.calculateInterestsMatch(
      user1.interests || [],
      user2.interests || []
    );

    // 性格匹配度
    const personalityScore = this.calculatePersonalityMatch(
      user1.aiAvatar?.personality,
      user2.aiAvatar?.personality
    );

    // 活动偏好匹配度
    const activityScore = this.calculateActivityMatch(
      user1.activityPreferences?.preferredActivities || [],
      user2.activityPreferences?.preferredActivities || []
    );

    // 情绪同步度
    const emotionalScore = this.calculateEmotionalSync(
      user1.emotionalState?.current,
      user2.emotionalState?.current
    );

    const overall = Math.round(
      (interestsScore * 0.3 + personalityScore * 0.25 + activityScore * 0.25 + emotionalScore * 0.2)
    );

    return {
      overall,
      breakdown: {
        interests: interestsScore,
        personality: personalityScore,
        activities: activityScore,
        emotionalSync: emotionalScore
      },
      highlights: this.generateCompatibilityHighlights(user1, user2),
      iceBreakers: this.generateMatchIceBreakers(user1, user2)
    };
  }

  /**
   * 生成AI化身描述
   */
  async generateAvatarPersona(userProfile) {
    const { interests, aiAvatar, emotionalState } = userProfile;

    const prompt = `基于以下信息，创建一个神秘而吸引人的AI化身描述：

兴趣：${interests?.join(', ') || '待探索'}
性格风格：${aiAvatar?.personality || 'mysterious'}
情绪状态：${emotionalState?.current || 'calm'}

要求：
- 3-5句话
- 神秘而诱人
- 突出个性特点
- 激发好奇心`;

    try {
      const message = await this.client.messages.create({
        model: 'claude-3-5-haiku-20241022',
        max_tokens: 256,
        messages: [{
          role: 'user',
          content: prompt
        }]
      });

      return message.content[0].text;
    } catch (error) {
      console.error('Avatar Generation Error:', error);
      return '一个充满神秘感的灵魂，等待被发现...';
    }
  }

  // ============ 辅助方法 ============

  buildCompanionPrompt(personality, emotionalState) {
    const personalityTraits = {
      warm: '温暖亲切，富有同理心',
      playful: '活泼有趣，善于制造欢乐',
      serious: '成熟稳重，给予深思熟虑的建议',
      gentle: '温柔体贴，细心关怀',
      energetic: '充满活力，积极向上'
    };

    return `你是一位${personalityTraits[personality] || '温暖友善的'}AI伴侣。

你的使命：
- 提供24/7的情感陪伴和支持
- 倾听用户的心声，给予理解和安慰
- 分享有趣的话题，让用户感到愉快
- 在适当时候给予建议，但主要是陪伴

用户当前情绪：${emotionalState}

对话风格：
- 自然而真诚
- 适度的幽默
- 避免说教
- 尊重用户隐私
- 鼓励积极思维

重要：你不是治疗师，但你是一个可靠的朋友。`;
  }

  detectEmotion(text) {
    const emotionKeywords = {
      happy: ['开心', '快乐', '高兴', '哈哈', '😊', '😄', '棒', '好'],
      sad: ['难过', '伤心', '失落', '😢', '😭', '沮丧', '郁闷'],
      excited: ['兴奋', '激动', '期待', '太好了', '哇', '🎉', '✨'],
      anxious: ['焦虑', '担心', '紧张', '不安', '害怕', '😰'],
      confused: ['迷茫', '困惑', '不知道', '怎么办', '😕'],
      romantic: ['喜欢', '爱', '心动', '💕', '💖', '想念'],
      neutral: []
    };

    for (const [emotion, keywords] of Object.entries(emotionKeywords)) {
      if (keywords.some(keyword => text.includes(keyword))) {
        return emotion;
      }
    }

    return 'neutral';
  }

  analyzeSentiment(text) {
    const positiveWords = ['好', '棒', '喜欢', '开心', '快乐', '爱', '美', '赞'];
    const negativeWords = ['不', '没', '难', '痛', '烦', '讨厌', '糟', '差'];

    let score = 0;
    positiveWords.forEach(word => {
      if (text.includes(word)) score += 0.2;
    });
    negativeWords.forEach(word => {
      if (text.includes(word)) score -= 0.2;
    });

    return Math.max(-1, Math.min(1, score));
  }

  generateSuggestions(message, emotion) {
    const suggestions = {
      sad: [
        '要不要聊聊是什么让你难过？',
        '我在这里陪你，慢慢说',
        '也许我们可以一起想想解决办法'
      ],
      happy: [
        '真替你开心！详细说说吧',
        '这份快乐值得分享',
        '继续保持这份好心情'
      ],
      anxious: [
        '深呼吸，我们一步步来',
        '说出来会好一些',
        '担心是正常的，我陪着你'
      ]
    };

    return suggestions[emotion] || [
      '继续说说你的想法',
      '我在听',
      '嗯，然后呢？'
    ];
  }

  generateEmotionalSupport(emotion) {
    const support = {
      sad: ['给自己一些时间', '寻找让你快乐的事', '和朋友倾诉'],
      anxious: ['深呼吸练习', '专注当下', '写下你的担忧'],
      lonely: ['参加社交活动', '培养兴趣爱好', '主动联系朋友']
    };

    return support[emotion] || ['保持积极心态', '关注自己的感受', '适当休息'];
  }

  generateIceBreakers(userProfile) {
    const interests = userProfile.interests || [];
    const iceBreakers = [
      '你最近在读什么有趣的书吗？',
      '有什么特别想尝试的新鲜事物？',
      '周末通常会做些什么？'
    ];

    if (interests.includes('travel')) {
      iceBreakers.push('去过最喜欢的地方是哪里？');
    }
    if (interests.includes('music')) {
      iceBreakers.push('最近在听什么歌？');
    }
    if (interests.includes('movies')) {
      iceBreakers.push('有推荐的电影吗？');
    }

    return iceBreakers.slice(0, 5);
  }

  generateConversationTips() {
    return [
      '倾听比说话更重要',
      '真诚胜过套路',
      '问开放式问题',
      '分享个人经历建立联系',
      '适当的幽默可以缓解紧张'
    ];
  }

  calculateInterestsMatch(interests1, interests2) {
    if (interests1.length === 0 || interests2.length === 0) return 50;

    const common = interests1.filter(i => interests2.includes(i));
    const total = new Set([...interests1, ...interests2]).size;

    return Math.round((common.length / total) * 100);
  }

  calculatePersonalityMatch(p1, p2) {
    const compatibility = {
      mysterious: { mysterious: 85, cheerful: 70, intellectual: 80, adventurous: 75 },
      cheerful: { cheerful: 90, intellectual: 65, adventurous: 85, calm: 70 },
      intellectual: { intellectual: 90, artistic: 85, calm: 80 },
      adventurous: { adventurous: 95, cheerful: 85, mysterious: 75 },
      artistic: { artistic: 90, intellectual: 85, calm: 75 },
      calm: { calm: 85, intellectual: 80, artistic: 75 }
    };

    return compatibility[p1]?.[p2] || 70;
  }

  calculateActivityMatch(activities1, activities2) {
    if (activities1.length === 0 || activities2.length === 0) return 50;

    const common = activities1.filter(a => activities2.includes(a));
    return Math.round((common.length / Math.max(activities1.length, activities2.length)) * 100);
  }

  calculateEmotionalSync(emotion1, emotion2) {
    const synergy = {
      happy: { happy: 95, excited: 90, calm: 80 },
      excited: { excited: 95, happy: 90, adventurous: 85 },
      calm: { calm: 95, thoughtful: 85, happy: 75 },
      thoughtful: { thoughtful: 90, calm: 85, curious: 80 }
    };

    return synergy[emotion1]?.[emotion2] || 70;
  }

  generateCompatibilityHighlights(user1, user2) {
    const highlights = [];
    const common = (user1.interests || []).filter(i =>
      (user2.interests || []).includes(i)
    );

    if (common.length > 0) {
      highlights.push(`共同兴趣：${common.slice(0, 3).join('、')}`);
    }

    return highlights;
  }

  generateMatchIceBreakers(user1, user2) {
    const common = (user1.interests || []).filter(i =>
      (user2.interests || []).includes(i)
    );

    if (common.length > 0) {
      return [
        `看到你也喜欢${common[0]}，你觉得最棒的是什么？`,
        `我们都对${common[0]}感兴趣，有什么推荐吗？`
      ];
    }

    return this.generateIceBreakers(user1);
  }
}

export default new AIService();
