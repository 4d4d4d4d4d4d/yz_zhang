import mongoose from 'mongoose';
import dotenv from 'dotenv';
import User from '../models/User.js';
import Activity from '../models/Activity.js';
import Match from '../models/Match.js';
import Game from '../models/Game.js';

dotenv.config();

const seedDatabase = async () => {
  try {
    // 连接数据库
    await mongoose.connect(process.env.MONGODB_URI);
    console.log('✅ Connected to MongoDB');

    // 清空现有数据
    console.log('🗑️  Clearing existing data...');
    await User.deleteMany({});
    await Activity.deleteMany({});
    await Match.deleteMany({});
    await Game.deleteMany({});

    // 创建测试用户
    console.log('👤 Creating users...');
    const users = await User.insertMany([
      {
        username: 'alice',
        email: 'alice@example.com',
        password: 'password123',
        profile: {
          displayName: '爱丽丝',
          age: 25,
          gender: 'female',
          bio: '喜欢旅行和摄影的神秘女孩',
          location: { city: '北京', country: '中国' }
        },
        interests: ['travel', 'photography', 'movies', 'music', 'art'],
        aiAvatar: {
          personality: 'mysterious',
          avatarStyle: 'abstract',
          voiceTone: 'warm',
          mysteryLevel: 4
        },
        activityPreferences: {
          preferredActivities: ['museum', 'cafe-hopping', 'photography-walk'],
          availability: { weekdays: false, weekends: true, evenings: true },
          groupSize: 'small-group'
        },
        isVerified: true
      },
      {
        username: 'bob',
        email: 'bob@example.com',
        password: 'password123',
        profile: {
          displayName: '鲍勃',
          age: 28,
          gender: 'male',
          bio: '热爱运动和音乐的阳光男孩',
          location: { city: '上海', country: '中国' }
        },
        interests: ['sports', 'music', 'hiking', 'gaming', 'cooking'],
        aiAvatar: {
          personality: 'cheerful',
          avatarStyle: 'realistic',
          voiceTone: 'energetic',
          mysteryLevel: 2
        },
        activityPreferences: {
          preferredActivities: ['sports', 'hiking', 'concert'],
          availability: { weekdays: true, weekends: true, evenings: true },
          groupSize: 'any'
        },
        isVerified: true
      },
      {
        username: 'charlie',
        email: 'charlie@example.com',
        password: 'password123',
        profile: {
          displayName: '查理',
          age: 26,
          gender: 'male',
          bio: '程序员，喜欢阅读和咖啡',
          location: { city: '北京', country: '中国' }
        },
        interests: ['technology', 'reading', 'coffee', 'gaming', 'movies'],
        aiAvatar: {
          personality: 'intellectual',
          avatarStyle: 'cartoon',
          voiceTone: 'gentle',
          mysteryLevel: 3
        },
        activityPreferences: {
          preferredActivities: ['cafe-hopping', 'board-games', 'museum'],
          availability: { weekdays: false, weekends: true, evenings: true },
          groupSize: 'one-on-one'
        },
        isVerified: true
      },
      {
        username: 'diana',
        email: 'diana@example.com',
        password: 'password123',
        profile: {
          displayName: '戴安娜',
          age: 24,
          gender: 'female',
          bio: '艺术家，追求美和创意',
          location: { city: '杭州', country: '中国' }
        },
        interests: ['art', 'photography', 'dancing', 'music', 'fashion'],
        aiAvatar: {
          personality: 'artistic',
          avatarStyle: 'abstract',
          voiceTone: 'playful',
          mysteryLevel: 5
        },
        activityPreferences: {
          preferredActivities: ['art-gallery', 'photography-walk', 'dancing'],
          availability: { weekdays: true, weekends: true, evenings: false },
          groupSize: 'small-group'
        },
        isVerified: true
      },
      {
        username: 'evan',
        email: 'evan@example.com',
        password: 'password123',
        profile: {
          displayName: '埃文',
          age: 29,
          gender: 'male',
          bio: '冒险家，喜欢探索未知',
          location: { city: '成都', country: '中国' }
        },
        interests: ['travel', 'hiking', 'camping', 'photography', 'sports'],
        aiAvatar: {
          personality: 'adventurous',
          avatarStyle: 'realistic',
          voiceTone: 'energetic',
          mysteryLevel: 2
        },
        activityPreferences: {
          preferredActivities: ['camping', 'hiking', 'sports'],
          availability: { weekdays: true, weekends: true, evenings: false },
          groupSize: 'large-group'
        },
        isVerified: true
      }
    ]);

    console.log(`✅ Created ${users.length} users`);

    // 创建活动
    console.log('🎯 Creating activities...');
    const activities = await Activity.insertMany([
      {
        title: '周末咖啡探店',
        description: '一起探索城市里的特色咖啡店，享受慢生活',
        type: 'cafe-hopping',
        schedule: {
          startTime: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7天后
          endTime: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000 + 4 * 60 * 60 * 1000), // +4小时
          duration: 240
        },
        location: {
          name: '三里屯',
          address: '朝阳区三里屯',
          city: '北京',
          coordinates: { lat: 39.9392, lng: 116.4466 }
        },
        participants: {
          min: 3,
          max: 8,
          current: [{ user: users[0]._id, status: 'confirmed' }]
        },
        mysteryMode: {
          enabled: true,
          revealTime: new Date(Date.now() + 6 * 24 * 60 * 60 * 1000),
          surpriseElement: '神秘咖啡师将为大家准备特调饮品'
        },
        cost: { amount: 0, currency: 'CNY' },
        tags: ['咖啡', '社交', '城市探索'],
        organizer: users[0]._id,
        isSystemGenerated: false,
        status: 'published'
      },
      {
        title: '香山徒步之旅',
        description: '登山健身，欣赏秋色，呼吸新鲜空气',
        type: 'hiking',
        schedule: {
          startTime: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000),
          endTime: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000 + 6 * 60 * 60 * 1000),
          duration: 360
        },
        location: {
          name: '香山公园',
          address: '海淀区香山路',
          city: '北京',
          coordinates: { lat: 40.0047, lng: 116.1881 }
        },
        participants: {
          min: 5,
          max: 15,
          current: [
            { user: users[1]._id, status: 'confirmed' },
            { user: users[4]._id, status: 'confirmed' }
          ]
        },
        mysteryMode: { enabled: false },
        cost: { amount: 0, currency: 'CNY' },
        tags: ['户外', '运动', '健康'],
        difficulty: 'moderate',
        organizer: users[1]._id,
        status: 'published'
      },
      {
        title: '现代艺术馆参观',
        description: '探索当代艺术，分享艺术见解',
        type: 'art-gallery',
        schedule: {
          startTime: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000),
          endTime: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000 + 3 * 60 * 60 * 1000),
          duration: 180
        },
        location: {
          name: 'UCCA当代艺术中心',
          address: '朝阳区酒仙桥路4号',
          city: '北京',
          coordinates: { lat: 39.9987, lng: 116.5009 }
        },
        participants: {
          min: 2,
          max: 6,
          current: [{ user: users[3]._id, status: 'confirmed' }]
        },
        mysteryMode: {
          enabled: true,
          revealTime: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000),
          surpriseElement: '特邀艺术家将现场分享创作心得'
        },
        cost: { amount: 60, currency: 'CNY', includes: ['门票', '讲解'] },
        tags: ['艺术', '文化', '社交'],
        organizer: users[3]._id,
        status: 'published'
      },
      {
        title: '剧本杀：谁是凶手',
        description: '沉浸式推理游戏，考验你的推理能力',
        type: 'escape-room',
        schedule: {
          startTime: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000),
          endTime: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000 + 4 * 60 * 60 * 1000),
          duration: 240
        },
        location: {
          name: '推理社剧本杀',
          address: '海淀区中关村大街',
          city: '北京',
          coordinates: { lat: 39.9822, lng: 116.3148 }
        },
        participants: {
          min: 6,
          max: 8,
          current: [
            { user: users[2]._id, status: 'confirmed' },
            { user: users[0]._id, status: 'confirmed' }
          ]
        },
        mysteryMode: {
          enabled: true,
          revealTime: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000),
          surpriseElement: '每个人都有秘密，真相只有一个'
        },
        cost: { amount: 120, currency: 'CNY', includes: ['剧本', '场地', '道具'] },
        tags: ['游戏', '推理', '社交'],
        difficulty: 'hard',
        organizer: users[2]._id,
        status: 'published'
      },
      {
        title: '周末野营',
        description: '远离城市喧嚣，回归自然',
        type: 'camping',
        schedule: {
          startTime: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
          endTime: new Date(Date.now() + 15 * 24 * 60 * 60 * 1000),
          duration: 1440
        },
        location: {
          name: '怀柔雁栖湖',
          address: '怀柔区雁栖湖',
          city: '北京',
          coordinates: { lat: 40.3834, lng: 116.6711 }
        },
        participants: {
          min: 6,
          max: 12,
          current: [{ user: users[4]._id, status: 'confirmed' }]
        },
        mysteryMode: { enabled: false },
        cost: { amount: 200, currency: 'CNY', includes: ['场地', '帐篷', '烧烤'] },
        tags: ['户外', '露营', '自然'],
        difficulty: 'easy',
        organizer: users[4]._id,
        status: 'published'
      }
    ]);

    console.log(`✅ Created ${activities.length} activities`);

    // 创建匹配
    console.log('💕 Creating matches...');
    const matches = await Match.insertMany([
      {
        users: [users[0]._id, users[2]._id],
        compatibility: {
          overall: 82,
          breakdown: {
            interests: 75,
            personality: 85,
            activities: 80,
            emotionalSync: 88
          }
        },
        status: 'accepted',
        mysteryMode: {
          enabled: true,
          revealStage: 2,
          unlockedInfo: ['interests', 'age']
        },
        interactions: {
          messages: 45,
          gamesPlayed: [
            {
              gameName: 'ice-breaker-cards',
              playedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000)
            }
          ]
        }
      },
      {
        users: [users[1]._id, users[4]._id],
        compatibility: {
          overall: 78,
          breakdown: {
            interests: 80,
            personality: 70,
            activities: 85,
            emotionalSync: 75
          }
        },
        status: 'pending',
        mysteryMode: {
          enabled: true,
          revealStage: 0,
          unlockedInfo: []
        },
        interactions: {
          messages: 0
        }
      }
    ]);

    console.log(`✅ Created ${matches.length} matches`);

    console.log('\n🎉 Database seeded successfully!');
    console.log('\n📝 Test accounts:');
    console.log('  Email: alice@example.com | Password: password123');
    console.log('  Email: bob@example.com | Password: password123');
    console.log('  Email: charlie@example.com | Password: password123');
    console.log('  Email: diana@example.com | Password: password123');
    console.log('  Email: evan@example.com | Password: password123');

    process.exit(0);
  } catch (error) {
    console.error('❌ Error seeding database:', error);
    process.exit(1);
  }
};

// 运行种子脚本
seedDatabase();
