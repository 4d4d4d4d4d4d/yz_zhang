# 神秘邂逅 - 安装与配置指南

## 前置要求

确保你的系统已安装以下软件：

- **Node.js** (v18 或更高版本)
- **MongoDB** (v6.0 或更高版本)
- **npm** 或 **yarn** 包管理器

## 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd dating-app
```

### 2. 安装依赖

#### 后端依赖

```bash
cd backend
npm install
```

#### 前端依赖

```bash
cd ../frontend
npm install
```

### 3. 配置环境变量

#### 后端配置

在 `backend` 目录创建 `.env` 文件：

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，填入以下配置：

```env
# 服务器端口
PORT=5000

# MongoDB 连接字符串
MONGODB_URI=mongodb://localhost:27017/dating-app

# JWT 密钥（请更改为随机字符串）
JWT_SECRET=your-super-secret-jwt-key-please-change-this

# Anthropic API 密钥（用于AI功能）
ANTHROPIC_API_KEY=sk-ant-xxx-your-api-key-here

# 前端 URL
CLIENT_URL=http://localhost:5173
```

#### 前端配置

在 `frontend` 目录创建 `.env` 文件：

```bash
cd ../frontend
cp .env.example .env
```

编辑 `.env` 文件：

```env
VITE_API_URL=http://localhost:5000/api
```

### 4. 启动 MongoDB

确保 MongoDB 服务正在运行：

```bash
# macOS (使用 Homebrew)
brew services start mongodb-community

# Ubuntu/Debian
sudo systemctl start mongod

# Windows
# 在服务管理器中启动 MongoDB 服务
```

### 5. 启动应用

#### 方法一：分别启动（推荐开发环境）

打开两个终端窗口：

**终端 1 - 启动后端：**

```bash
cd backend
npm run dev
```

后端将在 `http://localhost:5000` 启动

**终端 2 - 启动前端：**

```bash
cd frontend
npm run dev
```

前端将在 `http://localhost:5173` 启动

#### 方法二：生产环境启动

```bash
# 构建前端
cd frontend
npm run build

# 启动后端（可配置静态文件服务）
cd ../backend
npm start
```

### 6. 访问应用

在浏览器中打开：

```
http://localhost:5173
```

## 配置说明

### 获取 Anthropic API 密钥

1. 访问 [Anthropic Console](https://console.anthropic.com/)
2. 注册/登录账号
3. 创建新的 API 密钥
4. 复制密钥到 `backend/.env` 的 `ANTHROPIC_API_KEY`

### MongoDB 配置

#### 本地 MongoDB

默认配置使用本地 MongoDB：

```env
MONGODB_URI=mongodb://localhost:27017/dating-app
```

#### MongoDB Atlas (云数据库)

如果使用 MongoDB Atlas：

1. 创建免费集群
2. 获取连接字符串
3. 替换 `.env` 中的 `MONGODB_URI`：

```env
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/dating-app?retryWrites=true&w=majority
```

### JWT 密钥生成

生成安全的 JWT 密钥：

```bash
# 方法 1：使用 Node.js
node -e "console.log(require('crypto').randomBytes(64).toString('hex'))"

# 方法 2：使用 OpenSSL
openssl rand -hex 64
```

## 常见问题

### 1. MongoDB 连接失败

**错误：** `MongoNetworkError: connect ECONNREFUSED`

**解决方案：**
- 确保 MongoDB 服务正在运行
- 检查 `MONGODB_URI` 是否正确
- 检查防火墙设置

### 2. 端口被占用

**错误：** `Error: listen EADDRINUSE: address already in use :::5000`

**解决方案：**
```bash
# 查找占用端口的进程
lsof -i :5000

# 杀死进程
kill -9 <PID>

# 或者更改 .env 中的 PORT
```

### 3. API 密钥无效

**错误：** `AI companion service unavailable`

**解决方案：**
- 检查 `ANTHROPIC_API_KEY` 是否正确
- 确认 API 密钥有效且有足够的额度
- 检查网络连接

### 4. CORS 错误

**解决方案：**
- 确保 `backend/.env` 中的 `CLIENT_URL` 与前端地址一致
- 检查后端 CORS 配置

## 开发建议

### 推荐的开发工具

- **代码编辑器：** VS Code
- **API 测试：** Postman 或 Insomnia
- **数据库管理：** MongoDB Compass
- **Git 客户端：** GitHub Desktop

### VS Code 扩展推荐

```json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "mongodb.mongodb-vscode",
    "bradlc.vscode-tailwindcss",
    "dsznajder.es7-react-js-snippets"
  ]
}
```

### 开发模式特性

- 热重载（Hot Reload）
- 自动重启后端（nodemon）
- 快速刷新前端（Vite HMR）
- 详细的错误日志

## 下一步

1. 📖 阅读 [API 文档](./API.md)
2. 🎨 查看 [设计规范](./DESIGN.md)
3. 🔧 了解 [架构设计](./ARCHITECTURE.md)
4. 🚀 开始开发新功能！

## 获取帮助

- 📝 提交 [Issue](https://github.com/your-repo/issues)
- 💬 加入开发者社区
- 📧 联系技术支持

---

**祝你开发愉快！** ✨
