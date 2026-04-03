import PartyRoom from '../models/PartyRoom.js';
import User from '../models/User.js';

// Create party room
export const createPartyRoom = async (req, res) => {
  try {
    const {
      name,
      description,
      type,
      theme,
      maxParticipants,
      settings,
      silentMode
    } = req.body;

    // Initialize seats for voice rooms
    const seats = [];
    if (type === 'voice') {
      const seatCount = Math.min(maxParticipants || 8, 12);
      for (let i = 1; i <= seatCount; i++) {
        seats.push({
          number: i,
          occupiedBy: null,
          isLocked: false
        });
      }
    }

    const room = new PartyRoom({
      name,
      description,
      host: req.userId,
      type: type || 'voice',
      theme: theme || 'casual',
      maxParticipants: maxParticipants || 8,
      settings: settings || {},
      silentMode: silentMode || {},
      seats,
      participants: [{
        user: req.userId,
        role: 'host',
        seatNumber: type === 'voice' ? 1 : null
      }]
    });

    // Host takes first seat in voice rooms
    if (type === 'voice' && seats.length > 0) {
      seats[0].occupiedBy = req.userId;
    }

    await room.save();
    await room.populate('host', 'username profile.displayName profile.aiAvatar profile.photos');
    await room.populate('participants.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '房间创建成功', room });
  } catch (error) {
    console.error('Create party room error:', error);
    res.status(500).json({ error: '创建房间失败' });
  }
};

// Get active rooms
export const getActiveRooms = async (req, res) => {
  try {
    const { type, theme, page = 1, limit = 20 } = req.query;
    const skip = (page - 1) * limit;

    const query = {
      status: 'active',
      'settings.isPrivate': false
    };

    if (type) query.type = type;
    if (theme) query.theme = theme;

    const rooms = await PartyRoom.find(query)
      .populate('host', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('participants.user', 'username profile.displayName profile.aiAvatar')
      .sort({ 'stats.peakParticipants': -1, createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit));

    const total = await PartyRoom.countDocuments(query);

    res.json({
      rooms,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Get active rooms error:', error);
    res.status(500).json({ error: '获取房间列表失败' });
  }
};

// Get room details
export const getRoomDetails = async (req, res) => {
  try {
    const { roomId } = req.params;

    const room = await PartyRoom.findById(roomId)
      .populate('host', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('participants.user', 'username profile.displayName profile.aiAvatar profile.photos')
      .populate('seats.occupiedBy', 'username profile.displayName profile.aiAvatar')
      .populate('messages.user', 'username profile.displayName profile.aiAvatar');

    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    res.json({ room });
  } catch (error) {
    console.error('Get room details error:', error);
    res.status(500).json({ error: '获取房间详情失败' });
  }
};

// Join room
export const joinRoom = async (req, res) => {
  try {
    const { roomId } = req.params;
    const { password } = req.body;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    if (room.status !== 'active') {
      return res.status(400).json({ error: '房间已关闭' });
    }

    if (room.bannedUsers.includes(req.userId)) {
      return res.status(403).json({ error: '您已被禁止进入此房间' });
    }

    if (room.settings.password && room.settings.password !== password) {
      return res.status(401).json({ error: '密码错误' });
    }

    room.addParticipant(req.userId);

    // Add system message
    room.addMessage(room.host, `用户加入了房间`, 'system');

    await room.save();
    await room.populate('participants.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '加入房间成功', room });
  } catch (error) {
    console.error('Join room error:', error);
    res.status(400).json({ error: error.message || '加入房间失败' });
  }
};

// Leave room
export const leaveRoom = async (req, res) => {
  try {
    const { roomId } = req.params;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    room.removeParticipant(req.userId);

    // Add system message
    room.addMessage(room.host, `用户离开了房间`, 'system');

    // End room if host leaves and no participants
    if (room.host.toString() === req.userId && room.participants.length === 0) {
      room.status = 'ended';
    }

    await room.save();

    res.json({ message: '离开房间成功' });
  } catch (error) {
    console.error('Leave room error:', error);
    res.status(500).json({ error: '离开房间失败' });
  }
};

// Take seat
export const takeSeat = async (req, res) => {
  try {
    const { roomId } = req.params;
    const { seatNumber } = req.body;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    room.takeSeat(req.userId, seatNumber);

    // Add system message
    room.addMessage(room.host, `用户上麦了`, 'system');

    await room.save();
    await room.populate('seats.occupiedBy', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '上麦成功', seats: room.seats });
  } catch (error) {
    console.error('Take seat error:', error);
    res.status(400).json({ error: error.message || '上麦失败' });
  }
};

// Leave seat
export const leaveSeat = async (req, res) => {
  try {
    const { roomId } = req.params;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    room.leaveSeat(req.userId);

    // Add system message
    room.addMessage(room.host, `用户下麦了`, 'system');

    await room.save();
    await room.populate('seats.occupiedBy', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '下麦成功', seats: room.seats });
  } catch (error) {
    console.error('Leave seat error:', error);
    res.status(500).json({ error: '下麦失败' });
  }
};

// Send message
export const sendRoomMessage = async (req, res) => {
  try {
    const { roomId } = req.params;
    const { content, type = 'text' } = req.body;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    const isParticipant = room.participants.some(p => p.user.toString() === req.userId);
    if (!isParticipant) {
      return res.status(403).json({ error: '只有房间成员可以发送消息' });
    }

    room.addMessage(req.userId, content, type);
    await room.save();

    const message = room.messages[room.messages.length - 1];
    await room.populate('messages.user', 'username profile.displayName profile.aiAvatar');

    res.json({ message: '消息已发送', chat: message });
  } catch (error) {
    console.error('Send room message error:', error);
    res.status(500).json({ error: '发送消息失败' });
  }
};

// Toggle mute
export const toggleMute = async (req, res) => {
  try {
    const { roomId, userId } = req.params;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    // Only host/admin can mute others
    const requester = room.participants.find(p => p.user.toString() === req.userId);
    if (!requester || (requester.role !== 'host' && requester.role !== 'admin')) {
      return res.status(403).json({ error: '无权操作' });
    }

    const participant = room.participants.find(p => p.user.toString() === userId);
    if (!participant) {
      return res.status(404).json({ error: '用户不在房间中' });
    }

    participant.isMuted = !participant.isMuted;
    await room.save();

    res.json({
      message: participant.isMuted ? '已静音' : '已取消静音',
      isMuted: participant.isMuted
    });
  } catch (error) {
    console.error('Toggle mute error:', error);
    res.status(500).json({ error: '操作失败' });
  }
};

// End room
export const endRoom = async (req, res) => {
  try {
    const { roomId } = req.params;

    const room = await PartyRoom.findById(roomId);
    if (!room) {
      return res.status(404).json({ error: '房间不存在' });
    }

    if (room.host.toString() !== req.userId) {
      return res.status(403).json({ error: '只有房主可以结束房间' });
    }

    room.status = 'ended';

    // Calculate total duration
    const duration = Math.floor((new Date() - room.createdAt) / 1000 / 60);
    room.stats.totalDuration = duration;

    await room.save();

    res.json({ message: '房间已结束', room });
  } catch (error) {
    console.error('End room error:', error);
    res.status(500).json({ error: '结束房间失败' });
  }
};
