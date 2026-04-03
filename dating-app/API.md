# API 文档

## 基础信息

- **Base URL:** `http://localhost:5000/api`
- **认证方式:** Bearer Token (JWT)
- **Content-Type:** `application/json`

## 认证

所有需要认证的接口都需要在请求头中包含 JWT token：

```
Authorization: Bearer <your-jwt-token>
```

---

## 认证接口 (`/api/auth`)

### 注册

创建新用户账号

- **URL:** `/api/auth/register`
- **Method:** `POST`
- **认证:** 不需要

**请求体：**

```json
{
  "username": "cooluser",
  "email": "user@example.com",
  "password": "password123",
  "profile": {
    "displayName": "Cool User",
    "age": 25,
    "gender": "male"
  },
  "interests": ["travel", "music", "movies"],
  "aiAvatar": {
    "personality": "mysterious",
    "avatarStyle": "abstract",
    "voiceTone": "warm"
  }
}
```

**响应：**

```json
{
  "message": "Registration successful",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "_id": "user_id",
    "username": "cooluser",
    "profile": { ... },
    ...
  }
}
```

### 登录

- **URL:** `/api/auth/login`
- **Method:** `POST`
- **认证:** 不需要

**请求体：**

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**响应：**

```json
{
  "message": "Login successful",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": { ... }
}
```

### 获取个人资料

- **URL:** `/api/auth/profile`
- **Method:** `GET`
- **认证:** 需要

**响应：**

```json
{
  "user": { ... }
}
```

### 更新个人资料

- **URL:** `/api/auth/profile`
- **Method:** `PUT`
- **认证:** 需要

**请求体：**

```json
{
  "profile": {
    "bio": "这是我的新简介"
  },
  "interests": ["travel", "photography"],
  "aiAvatar": {
    "personality": "cheerful"
  }
}
```

---

## AI 伴侣接口 (`/api/ai`)

### AI 伴侣聊天

与 AI 伴侣进行对话

- **URL:** `/api/ai/companion/chat`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "message": "今天心情有点低落"
}
```

**响应：**

```json
{
  "message": "听到你这么说我很担心，能跟我说说发生了什么吗？",
  "emotion": "sad",
  "sentiment": -0.3,
  "suggestions": [
    "要不要聊聊是什么让你难过？",
    "我在这里陪你，慢慢说"
  ],
  "conversationId": "conv_id"
}
```

### 获取约会建议

- **URL:** `/api/ai/dating-coach/advice`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "scenario": "我想约她出去，但不知道该说什么"
}
```

**响应：**

```json
{
  "advice": "...",
  "iceBreakers": ["..."],
  "conversationTips": ["..."]
}
```

### 情绪分析

- **URL:** `/api/ai/emotion/analyze`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "text": "今天真是太开心了！"
}
```

**响应：**

```json
{
  "emotion": "happy",
  "sentiment": 0.8,
  "confidence": 0.85,
  "suggestions": ["..."]
}
```

### 获取 AI 对话历史

- **URL:** `/api/ai/conversations`
- **Method:** `GET`
- **认证:** 需要

**响应：**

```json
{
  "conversations": [
    {
      "_id": "conv_id",
      "messages": [...],
      "lastMessageAt": "2024-01-01T00:00:00.000Z"
    }
  ]
}
```

### 生成破冰话题

- **URL:** `/api/ai/ice-breakers`
- **Method:** `GET`
- **认证:** 需要
- **查询参数:** `targetUserId` (可选)

**响应：**

```json
{
  "iceBreakers": [
    "你最近在读什么有趣的书吗？",
    "周末通常会做些什么？",
    "..."
  ]
}
```

---

## 匹配接口 (`/api/matches`)

### 获取推荐匹配

- **URL:** `/api/matches/recommendations`
- **Method:** `GET`
- **认证:** 需要
- **查询参数:**
  - `limit`: 数量限制 (默认: 10)
  - `mysteryMode`: 是否开启神秘模式 (默认: true)

**响应：**

```json
{
  "recommendations": [
    {
      "user": {
        "_id": "user_id",
        "interests": ["travel", "music"],
        "profile": { ... }
      },
      "compatibility": 85,
      "breakdown": {
        "interests": 90,
        "personality": 80,
        "activities": 85,
        "emotionalSync": 85
      },
      "highlights": ["共同兴趣：旅行、音乐"],
      "iceBreakers": ["..."]
    }
  ],
  "mysteryMode": true
}
```

### 创建匹配

向用户发送匹配请求

- **URL:** `/api/matches`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "targetUserId": "target_user_id"
}
```

**响应：**

```json
{
  "message": "Match created successfully",
  "match": { ... },
  "compatibility": 85
}
```

### 获取我的匹配列表

- **URL:** `/api/matches/my-matches`
- **Method:** `GET`
- **认证:** 需要
- **查询参数:** `status` (可选): pending, accepted, rejected

**响应：**

```json
{
  "matches": [
    {
      "_id": "match_id",
      "users": [...],
      "compatibility": { ... },
      "status": "pending",
      "mysteryMode": { ... }
    }
  ]
}
```

### 获取匹配详情

- **URL:** `/api/matches/:matchId`
- **Method:** `GET`
- **认证:** 需要

**响应：**

```json
{
  "match": {
    "_id": "match_id",
    "users": [...],
    "compatibility": { ... },
    "interactions": { ... },
    "mysteryMode": { ... }
  }
}
```

### 响应匹配请求

接受或拒绝匹配

- **URL:** `/api/matches/:matchId/respond`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "action": "accept"  // 或 "reject"
}
```

**响应：**

```json
{
  "message": "Match accepted successfully",
  "match": { ... }
}
```

### 解锁神秘信息

- **URL:** `/api/matches/:matchId/reveal`
- **Method:** `POST`
- **认证:** 需要

**响应：**

```json
{
  "message": "Mystery info revealed",
  "revealStage": 2,
  "unlockedInfo": ["age", "interests"],
  "match": { ... }
}
```

---

## 活动接口 (`/api/activities`)

### 获取活动列表

- **URL:** `/api/activities`
- **Method:** `GET`
- **认证:** 需要
- **查询参数:**
  - `type`: 活动类型
  - `city`: 城市
  - `startDate`: 开始日期
  - `endDate`: 结束日期
  - `mysteryMode`: 神秘模式
  - `limit`: 数量限制 (默认: 20)
  - `page`: 页码 (默认: 1)

**响应：**

```json
{
  "activities": [
    {
      "_id": "activity_id",
      "title": "周末咖啡探店",
      "description": "...",
      "type": "cafe-hopping",
      "schedule": {
        "startTime": "2024-01-15T14:00:00.000Z",
        "endTime": "2024-01-15T18:00:00.000Z"
      },
      "location": {
        "name": "三里屯",
        "city": "北京"
      },
      "participants": {
        "current": [...],
        "max": 10
      },
      "cost": {
        "amount": 0,
        "currency": "CNY"
      }
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 50,
    "pages": 3
  }
}
```

### 创建活动

- **URL:** `/api/activities`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "title": "周末徒步",
  "description": "一起去爬山",
  "type": "hiking",
  "schedule": {
    "startTime": "2024-01-20T08:00:00.000Z",
    "endTime": "2024-01-20T16:00:00.000Z"
  },
  "location": {
    "name": "香山",
    "city": "北京"
  },
  "participants": {
    "min": 4,
    "max": 10
  },
  "cost": {
    "amount": 0
  }
}
```

### 获取活动详情

- **URL:** `/api/activities/:activityId`
- **Method:** `GET`
- **认证:** 需要

### 报名参加活动

- **URL:** `/api/activities/:activityId/join`
- **Method:** `POST`
- **认证:** 需要

**响应：**

```json
{
  "message": "Successfully joined activity",
  "activity": { ... }
}
```

### 取消报名

- **URL:** `/api/activities/:activityId/leave`
- **Method:** `POST`
- **认证:** 需要

### 随机匹配活动

获取一个随机推荐的活动

- **URL:** `/api/activities/random`
- **Method:** `GET`
- **认证:** 需要

**响应：**

```json
{
  "activity": { ... },
  "message": "为你找到了一个神秘活动！",
  "mysteryElement": "等待你的到来..."
}
```

### 提交活动反馈

- **URL:** `/api/activities/:activityId/feedback`
- **Method:** `POST`
- **认证:** 需要

**请求体：**

```json
{
  "rating": 5,
  "comment": "很棒的体验！",
  "photos": ["url1", "url2"]
}
```

### 获取推荐活动

基于用户偏好推荐活动

- **URL:** `/api/activities/recommendations`
- **Method:** `GET`
- **认证:** 需要
- **查询参数:** `limit` (默认: 10)

**响应：**

```json
{
  "activities": [...],
  "recommendations": 6,
  "basedOn": {
    "interests": ["travel", "music"],
    "preferences": ["hiking", "cafe-hopping"]
  }
}
```

---

## 错误响应

所有错误响应都遵循以下格式：

```json
{
  "error": "Error message describing what went wrong"
}
```

### 常见错误代码

- `400` - Bad Request (请求参数错误)
- `401` - Unauthorized (未认证或 token 无效)
- `403` - Forbidden (无权限)
- `404` - Not Found (资源不存在)
- `500` - Internal Server Error (服务器错误)

---

## 实时通信 (Socket.io)

### 连接

```javascript
const socket = io('http://localhost:5000');

// 用户加入
socket.emit('user:join', userId);
```

### 事件

#### 发送消息

```javascript
socket.emit('message:send', {
  conversationId: 'conv_id',
  recipientId: 'recipient_id',
  message: 'Hello!'
});
```

#### 接收消息

```javascript
socket.on('message:received', (data) => {
  console.log('New message:', data);
});
```

#### 正在输入

```javascript
// 开始输入
socket.emit('typing:start', { recipientId: 'recipient_id' });

// 停止输入
socket.emit('typing:stop', { recipientId: 'recipient_id' });
```

#### 标记已读

```javascript
socket.emit('message:read', { conversationId: 'conv_id' });
```

---

## 速率限制

为了保护服务器资源，部分接口可能有速率限制：

- AI 相关接口：每分钟 20 次
- 匹配创建：每小时 100 次
- 一般 API：每分钟 100 次

超过限制会返回 `429 Too Many Requests`。

---

## 示例代码

### JavaScript (Fetch)

```javascript
// 登录
const login = async () => {
  const response = await fetch('http://localhost:5000/api/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      email: 'user@example.com',
      password: 'password123'
    })
  });

  const data = await response.json();
  const token = data.token;

  // 保存 token
  localStorage.setItem('token', token);
};

// 使用 token 发送请求
const getProfile = async () => {
  const token = localStorage.getItem('token');

  const response = await fetch('http://localhost:5000/api/auth/profile', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  const data = await response.json();
  return data.user;
};
```

### cURL

```bash
# 注册
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@example.com","password":"123456"}'

# 登录
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"123456"}'

# 使用 token 获取资料
curl -X GET http://localhost:5000/api/auth/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

**API 文档持续更新中...** 📝
