import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 请求拦截器 - 添加token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ============ 认证API ============
export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  getProfile: () => api.get('/auth/profile'),
  updateProfile: (data) => api.put('/auth/profile', data)
};

// ============ AI伴侣API ============
export const aiAPI = {
  companionChat: (message) => api.post('/ai/companion/chat', { message }),
  getDatingAdvice: (scenario) => api.post('/ai/dating-coach/advice', { scenario }),
  analyzeEmotion: (text) => api.post('/ai/emotion/analyze', { text }),
  getConversations: () => api.get('/ai/conversations'),
  generateIceBreakers: (targetUserId) =>
    api.get('/ai/ice-breakers', { params: { targetUserId } }),
  getConversationTips: () => api.get('/ai/conversation-tips')
};

// ============ 匹配API ============
export const matchAPI = {
  getRecommendations: (params) => api.get('/matches/recommendations', { params }),
  createMatch: (targetUserId) => api.post('/matches', { targetUserId }),
  getMyMatches: (status) => api.get('/matches/my-matches', { params: { status } }),
  getMatchDetails: (matchId) => api.get(`/matches/${matchId}`),
  respondToMatch: (matchId, action) =>
    api.post(`/matches/${matchId}/respond`, { action }),
  revealMysteryInfo: (matchId) => api.post(`/matches/${matchId}/reveal`)
};

// ============ 活动API ============
export const activityAPI = {
  getActivities: (params) => api.get('/activities', { params }),
  createActivity: (data) => api.post('/activities', data),
  getActivityDetails: (activityId) => api.get(`/activities/${activityId}`),
  joinActivity: (activityId) => api.post(`/activities/${activityId}/join`),
  leaveActivity: (activityId) => api.post(`/activities/${activityId}/leave`),
  getRandomActivity: () => api.get('/activities/random'),
  submitFeedback: (activityId, data) =>
    api.post(`/activities/${activityId}/feedback`, data),
  getRecommendedActivities: (limit) =>
    api.get('/activities/recommendations', { params: { limit } })
};

// ============ 游戏API ============
export const gameAPI = {
  createGame: (data) => api.post('/games', data),
  getPublicGames: (params) => api.get('/games/public', { params }),
  getMyGames: (status) => api.get('/games/my-games', { params: { status } }),
  getGameDetails: (gameId) => api.get(`/games/${gameId}`),
  joinGame: (gameId) => api.post(`/games/${gameId}/join`),
  startGame: (gameId) => api.post(`/games/${gameId}/start`),
  getQuestion: (gameId, questionType) =>
    api.get(`/games/${gameId}/question`, { params: { questionType } }),
  submitAnswer: (gameId, data) => api.post(`/games/${gameId}/answer`, data),
  getPersonalityTest: () => api.get('/games/personality-test/questions'),
  submitPersonalityTest: (gameId, answers) =>
    api.post(`/games/${gameId}/personality-test`, { answers }),
  endGame: (gameId) => api.post(`/games/${gameId}/end`),
  rateGame: (gameId, rating) => api.post(`/games/${gameId}/rate`, { rating })
};

// ============ 通知API ============
export const notificationAPI = {
  getNotifications: (params) => api.get('/notifications', { params }),
  getUnreadCount: () => api.get('/notifications/unread-count'),
  markAsRead: (notificationId) => api.patch(`/notifications/${notificationId}/read`),
  markAllAsRead: () => api.post('/notifications/mark-all-read'),
  deleteNotification: (notificationId) => api.delete(`/notifications/${notificationId}`),
  clearReadNotifications: () => api.delete('/notifications/clear-read')
};

// ============ 用户API ============
export const userAPI = {
  searchUsers: (params) => api.get('/users/search', { params }),
  getRecommendedUsers: (limit) => api.get('/users/recommended', { params: { limit } }),
  getUserProfile: (userId) => api.get(`/users/${userId}`),
  getOnlineUsers: (limit) => api.get('/users/online', { params: { limit } }),
  getNearbyUsers: (limit) => api.get('/users/nearby', { params: { limit } }),
  getPopularUsers: (limit) => api.get('/users/popular', { params: { limit } })
};

// ============ 安全API ============
export const safetyAPI = {
  blockUser: (userId, data) => api.post(`/safety/block/${userId}`, data),
  unblockUser: (userId) => api.delete(`/safety/block/${userId}`),
  getBlockedUsers: (params) => api.get('/safety/blocked', { params }),
  checkBlocked: (userId) => api.get(`/safety/blocked/${userId}`),
  reportUser: (userId, data) => api.post(`/safety/report/${userId}`, data),
  getMyReports: (params) => api.get('/safety/reports', { params }),
  cancelReport: (reportId) => api.delete(`/safety/reports/${reportId}`)
};

// ============ 互动游戏API ============
export const interactiveGameAPI = {
  createGame: (data) => api.post('/interactive-games', data),
  getPublicGames: (params) => api.get('/interactive-games/public', { params }),
  getScriptTemplates: () => api.get('/interactive-games/templates/scripts'),
  getGameDetails: (gameId) => api.get(`/interactive-games/${gameId}`),
  joinGame: (gameId, data) => api.post(`/interactive-games/${gameId}/join`, data),
  startGame: (gameId) => api.post(`/interactive-games/${gameId}/start`),
  submitDrawing: (gameId, data) => api.post(`/interactive-games/${gameId}/drawing`, data),
  submitGuess: (gameId, data) => api.post(`/interactive-games/${gameId}/guess`, data),
  sendChat: (gameId, data) => api.post(`/interactive-games/${gameId}/chat`, data)
};

// ============ 瞬间API ============
export const momentAPI = {
  createMoment: (data) => api.post('/moments', data),
  getMomentsFeed: (params) => api.get('/moments/feed', { params }),
  getTrendingTopics: (params) => api.get('/moments/trending', { params }),
  getNearbyMoments: (params) => api.get('/moments/nearby', { params }),
  getUserMoments: (userId, params) => api.get(`/moments/user/${userId}`, { params }),
  getMomentById: (momentId) => api.get(`/moments/${momentId}`),
  deleteMoment: (momentId) => api.delete(`/moments/${momentId}`),
  toggleLike: (momentId) => api.post(`/moments/${momentId}/like`),
  addComment: (momentId, data) => api.post(`/moments/${momentId}/comment`, data),
  deleteComment: (momentId, commentId) => api.delete(`/moments/${momentId}/comment/${commentId}`),
  voteOnPoll: (momentId, data) => api.post(`/moments/${momentId}/vote`, data)
};

// ============ 派对房间API ============
export const partyRoomAPI = {
  createRoom: (data) => api.post('/party-rooms', data),
  getActiveRooms: (params) => api.get('/party-rooms/active', { params }),
  getRoomDetails: (roomId) => api.get(`/party-rooms/${roomId}`),
  joinRoom: (roomId, data) => api.post(`/party-rooms/${roomId}/join`, data),
  leaveRoom: (roomId) => api.post(`/party-rooms/${roomId}/leave`),
  endRoom: (roomId) => api.post(`/party-rooms/${roomId}/end`),
  takeSeat: (roomId, data) => api.post(`/party-rooms/${roomId}/seat`, data),
  leaveSeat: (roomId) => api.delete(`/party-rooms/${roomId}/seat`),
  sendMessage: (roomId, data) => api.post(`/party-rooms/${roomId}/message`, data),
  toggleMute: (roomId, userId) => api.post(`/party-rooms/${roomId}/mute/${userId}`)
};

export default api;
