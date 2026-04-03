import aiService from '../services/aiService.js';
import Conversation from '../models/Conversation.js';
import User from '../models/User.js';

/**
 * AI伴侣聊天
 */
export const companionChat = async (req, res) => {
  try {
    const { message } = req.body;
    const userId = req.userId;

    // 查找或创建AI对话
    let conversation = await Conversation.findOne({
      type: 'user-to-ai',
      participants: userId
    });

    if (!conversation) {
      conversation = new Conversation({
        type: 'user-to-ai',
        participants: [userId],
        aiCompanion: {
          personality: req.user.aiAvatar.personality,
          role: 'emotional-support'
        }
      });
    }

    // 构建对话历史
    const conversationHistory = conversation.messages.slice(-10).map(msg => ({
      role: msg.senderType === 'ai-companion' ? 'assistant' : 'user',
      content: msg.content.text
    }));

    // 获取AI响应
    const aiResponse = await aiService.companionChat(message, {
      personality: req.user.aiAvatar.voiceTone || 'warm',
      emotionalState: req.user.emotionalState.current,
      conversationHistory
    });

    // 保存用户消息
    conversation.addMessage({
      sender: userId,
      senderType: 'user',
      content: {
        text: message,
        type: 'text'
      },
      aiMetadata: {
        emotionDetected: aiResponse.emotion,
        sentiment: aiResponse.sentiment,
        suggestedResponses: aiResponse.suggestions
      }
    });

    // 保存AI响应
    conversation.addMessage({
      senderType: 'ai-companion',
      content: {
        text: aiResponse.response,
        type: 'text'
      }
    });

    await conversation.save();

    // 更新用户统计
    req.user.stats.aiConversations += 1;
    await req.user.save();

    res.json({
      message: aiResponse.response,
      emotion: aiResponse.emotion,
      sentiment: aiResponse.sentiment,
      suggestions: aiResponse.suggestions,
      conversationId: conversation._id
    });
  } catch (error) {
    console.error('AI Companion Chat Error:', error);
    res.status(500).json({ error: 'AI companion service unavailable' });
  }
};

/**
 * 约会教练建议
 */
export const getDatingAdvice = async (req, res) => {
  try {
    const { scenario } = req.body;
    const userProfile = req.user.toObject();

    const advice = await aiService.datingCoach(scenario, userProfile);

    res.json(advice);
  } catch (error) {
    console.error('Dating Coach Error:', error);
    res.status(500).json({ error: 'Dating coach service unavailable' });
  }
};

/**
 * 情绪分析
 */
export const analyzeEmotion = async (req, res) => {
  try {
    const { text } = req.body;

    const analysis = await aiService.analyzeEmotion(text);

    // 更新用户情绪状态
    req.user.emotionalState.current = analysis.emotion;
    req.user.emotionalState.history.push({
      mood: analysis.emotion,
      timestamp: new Date(),
      context: text.substring(0, 100)
    });

    // 只保留最近50条情绪记录
    if (req.user.emotionalState.history.length > 50) {
      req.user.emotionalState.history = req.user.emotionalState.history.slice(-50);
    }

    await req.user.save();

    res.json(analysis);
  } catch (error) {
    console.error('Emotion Analysis Error:', error);
    res.status(500).json({ error: 'Emotion analysis failed' });
  }
};

/**
 * 获取AI对话历史
 */
export const getAIConversations = async (req, res) => {
  try {
    const conversations = await Conversation.find({
      type: 'user-to-ai',
      participants: req.userId
    })
      .sort({ lastMessageAt: -1 })
      .limit(20);

    res.json({ conversations });
  } catch (error) {
    console.error('Get AI Conversations Error:', error);
    res.status(500).json({ error: 'Failed to get conversations' });
  }
};

/**
 * 生成破冰话题
 */
export const generateIceBreakers = async (req, res) => {
  try {
    const { targetUserId } = req.query;

    let iceBreakers;

    if (targetUserId) {
      // 为特定用户生成破冰话题
      const targetUser = await User.findById(targetUserId);
      if (!targetUser) {
        return res.status(404).json({ error: 'Target user not found' });
      }

      const compatibility = await aiService.analyzeCompatibility(
        req.user.toObject(),
        targetUser.toObject()
      );

      iceBreakers = compatibility.iceBreakers;
    } else {
      // 生成通用破冰话题
      iceBreakers = aiService.generateIceBreakers(req.user.toObject());
    }

    res.json({ iceBreakers });
  } catch (error) {
    console.error('Generate Ice Breakers Error:', error);
    res.status(500).json({ error: 'Failed to generate ice breakers' });
  }
};

/**
 * 获取对话建议
 */
export const getConversationTips = async (req, res) => {
  try {
    const tips = aiService.generateConversationTips();
    res.json({ tips });
  } catch (error) {
    console.error('Get Conversation Tips Error:', error);
    res.status(500).json({ error: 'Failed to get conversation tips' });
  }
};
