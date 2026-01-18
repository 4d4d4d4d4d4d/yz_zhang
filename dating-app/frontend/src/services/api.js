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

export default api;
