import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import useAuthStore from '../store/authStore';
import { authAPI } from '../services/api';

const Login = () => {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [formData, setFormData] = useState({
    email: '',
    password: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.login(formData);
      const { token, user } = response.data;
      setAuth(user, token);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || '登录失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          animate={{
            scale: [1, 1.2, 1],
            rotate: [0, 90, 0]
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: 'linear'
          }}
          className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl"
        />
        <motion.div
          animate={{
            scale: [1.2, 1, 1.2],
            rotate: [90, 0, 90]
          }}
          transition={{
            duration: 15,
            repeat: Infinity,
            ease: 'linear'
          }}
          className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl"
        />
      </div>

      {/* 登录表单 */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="mystery-card max-w-md w-full relative z-10"
      >
        <div className="text-center mb-8">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
            className="inline-block text-6xl mb-4"
          >
            ✨
          </motion.div>
          <h1 className="text-3xl font-bold gradient-text mb-2">神秘邂逅</h1>
          <p className="text-white/60">开启你的神秘之旅</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-red-500/20 border border-red-500/50 rounded-xl p-3 text-center text-red-200"
            >
              {error}
            </motion.div>
          )}

          <div>
            <label className="block text-sm font-medium mb-2 text-white/80">
              邮箱
            </label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              required
              className="mystery-input"
              placeholder="your@email.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-white/80">
              密码
            </label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required
              className="mystery-input"
              placeholder="••••••••"
            />
          </div>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={loading}
            className="w-full mystery-button"
          >
            {loading ? (
              <div className="flex items-center justify-center space-x-2">
                <div className="loader w-5 h-5 border-2" />
                <span>登录中...</span>
              </div>
            ) : (
              '登录'
            )}
          </motion.button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-white/60">
            还没有账号？{' '}
            <Link to="/register" className="text-purple-300 hover:text-purple-200 font-semibold">
              立即注册
            </Link>
          </p>
        </div>

        {/* 装饰性元素 */}
        <div className="absolute -top-10 -right-10 text-6xl opacity-20 animate-float">
          💫
        </div>
        <div className="absolute -bottom-10 -left-10 text-6xl opacity-20 animate-float" style={{ animationDelay: '1s' }}>
          💕
        </div>
      </motion.div>
    </div>
  );
};

export default Login;
