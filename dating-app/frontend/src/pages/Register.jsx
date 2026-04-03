import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import useAuthStore from '../store/authStore';
import { authAPI } from '../services/api';

const Register = () => {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    profile: {
      displayName: '',
      age: '',
      gender: 'prefer-not-to-say'
    },
    interests: [],
    aiAvatar: {
      personality: 'mysterious',
      avatarStyle: 'abstract',
      voiceTone: 'warm'
    }
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const interestOptions = [
    { value: 'travel', label: '旅行', icon: '✈️' },
    { value: 'reading', label: '阅读', icon: '📚' },
    { value: 'movies', label: '电影', icon: '🎬' },
    { value: 'music', label: '音乐', icon: '🎵' },
    { value: 'sports', label: '运动', icon: '⚽' },
    { value: 'gaming', label: '游戏', icon: '🎮' },
    { value: 'cooking', label: '烹饪', icon: '🍳' },
    { value: 'art', label: '艺术', icon: '🎨' },
    { value: 'photography', label: '摄影', icon: '📷' },
    { value: 'dancing', label: '舞蹈', icon: '💃' },
    { value: 'hiking', label: '徒步', icon: '🥾' },
    { value: 'yoga', label: '瑜伽', icon: '🧘' }
  ];

  const personalityOptions = [
    { value: 'mysterious', label: '神秘', desc: '充满未知的魅力' },
    { value: 'cheerful', label: '开朗', desc: '阳光活力满满' },
    { value: 'intellectual', label: '睿智', desc: '理性思考者' },
    { value: 'adventurous', label: '冒险', desc: '勇于探索' },
    { value: 'artistic', label: '艺术', desc: '富有创造力' },
    { value: 'calm', label: '沉静', desc: '内心平和' }
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.register(formData);
      const { token, user } = response.data;
      setAuth(user, token);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || '注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    if (name.includes('.')) {
      const [parent, child] = name.split('.');
      setFormData({
        ...formData,
        [parent]: {
          ...formData[parent],
          [child]: value
        }
      });
    } else {
      setFormData({
        ...formData,
        [name]: value
      });
    }
  };

  const toggleInterest = (interest) => {
    setFormData({
      ...formData,
      interests: formData.interests.includes(interest)
        ? formData.interests.filter(i => i !== interest)
        : [...formData.interests, interest]
    });
  };

  const nextStep = () => {
    setStep(step + 1);
  };

  const prevStep = () => {
    setStep(step - 1);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="mystery-card max-w-2xl w-full"
      >
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold gradient-text mb-2">创建你的神秘化身</h1>
          <p className="text-white/60">步骤 {step}/3</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-3 text-center text-red-200">
              {error}
            </div>
          )}

          {/* 步骤1: 基本信息 */}
          {step === 1 && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-4"
            >
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2 text-white/80">
                    用户名
                  </label>
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    required
                    className="mystery-input"
                    placeholder="选个酷炫的名字"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2 text-white/80">
                    显示名称
                  </label>
                  <input
                    type="text"
                    name="profile.displayName"
                    value={formData.profile.displayName}
                    onChange={handleChange}
                    className="mystery-input"
                    placeholder="别人看到的名字"
                  />
                </div>
              </div>

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
                  minLength={6}
                  className="mystery-input"
                  placeholder="至少6位"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2 text-white/80">
                    年龄
                  </label>
                  <input
                    type="number"
                    name="profile.age"
                    value={formData.profile.age}
                    onChange={handleChange}
                    min="18"
                    max="100"
                    className="mystery-input"
                    placeholder="18+"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2 text-white/80">
                    性别
                  </label>
                  <select
                    name="profile.gender"
                    value={formData.profile.gender}
                    onChange={handleChange}
                    className="mystery-input"
                  >
                    <option value="male">男</option>
                    <option value="female">女</option>
                    <option value="other">其他</option>
                    <option value="prefer-not-to-say">保密</option>
                  </select>
                </div>
              </div>

              <button
                type="button"
                onClick={nextStep}
                className="w-full mystery-button"
              >
                下一步 →
              </button>
            </motion.div>
          )}

          {/* 步骤2: 兴趣选择 */}
          {step === 2 && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-4"
            >
              <div>
                <h3 className="text-lg font-semibold mb-4">选择你的兴趣 (至少3个)</h3>
                <div className="grid grid-cols-3 gap-3">
                  {interestOptions.map((option) => (
                    <motion.button
                      key={option.value}
                      type="button"
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={() => toggleInterest(option.value)}
                      className={`p-4 rounded-xl border-2 transition-all ${
                        formData.interests.includes(option.value)
                          ? 'bg-gradient-mystery border-purple-400 shadow-lg'
                          : 'bg-white/5 border-white/20 hover:border-white/40'
                      }`}
                    >
                      <div className="text-3xl mb-2">{option.icon}</div>
                      <div className="text-sm">{option.label}</div>
                    </motion.button>
                  ))}
                </div>
              </div>

              <div className="flex space-x-4">
                <button
                  type="button"
                  onClick={prevStep}
                  className="flex-1 px-6 py-3 rounded-full bg-white/10 hover:bg-white/20 transition-all"
                >
                  ← 上一步
                </button>
                <button
                  type="button"
                  onClick={nextStep}
                  disabled={formData.interests.length < 3}
                  className="flex-1 mystery-button disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  下一步 →
                </button>
              </div>
            </motion.div>
          )}

          {/* 步骤3: AI化身 */}
          {step === 3 && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-6"
            >
              <div>
                <h3 className="text-lg font-semibold mb-4">选择你的AI性格</h3>
                <div className="grid grid-cols-2 gap-3">
                  {personalityOptions.map((option) => (
                    <motion.button
                      key={option.value}
                      type="button"
                      whileHover={{ scale: 1.02 }}
                      onClick={() =>
                        setFormData({
                          ...formData,
                          aiAvatar: { ...formData.aiAvatar, personality: option.value }
                        })
                      }
                      className={`p-4 rounded-xl border-2 text-left transition-all ${
                        formData.aiAvatar.personality === option.value
                          ? 'bg-gradient-mystery border-purple-400'
                          : 'bg-white/5 border-white/20 hover:border-white/40'
                      }`}
                    >
                      <div className="font-semibold mb-1">{option.label}</div>
                      <div className="text-xs text-white/60">{option.desc}</div>
                    </motion.button>
                  ))}
                </div>
              </div>

              <div className="flex space-x-4">
                <button
                  type="button"
                  onClick={prevStep}
                  className="flex-1 px-6 py-3 rounded-full bg-white/10 hover:bg-white/20 transition-all"
                >
                  ← 上一步
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 mystery-button"
                >
                  {loading ? '创建中...' : '完成创建 ✨'}
                </button>
              </div>
            </motion.div>
          )}
        </form>

        <div className="mt-6 text-center">
          <p className="text-white/60">
            已有账号？{' '}
            <Link to="/login" className="text-purple-300 hover:text-purple-200 font-semibold">
              立即登录
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default Register;
