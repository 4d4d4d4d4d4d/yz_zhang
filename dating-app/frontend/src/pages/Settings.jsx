import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { authAPI } from '../services/api';
import useAuthStore from '../store/authStore';
import {
  Cog6ToothIcon,
  UserCircleIcon,
  BellIcon,
  ShieldCheckIcon,
  EyeIcon,
  EyeSlashIcon,
  MapPinIcon,
  HeartIcon
} from '@heroicons/react/24/outline';

const Settings = () => {
  const { user, setUser } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  // Account settings
  const [accountSettings, setAccountSettings] = useState({
    email: '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });

  // Privacy settings
  const [privacySettings, setPrivacySettings] = useState({
    showAge: true,
    showLocation: true,
    showLastActive: true,
    allowMessages: true,
    visibleInSearch: true
  });

  // Match preferences
  const [matchPreferences, setMatchPreferences] = useState({
    ageRange: { min: 18, max: 50 },
    maxDistance: 50,
    genderPreference: 'all',
    mysteryMode: {
      enabled: true,
      revealSpeed: 'medium'
    }
  });

  // Notification preferences
  const [notificationSettings, setNotificationSettings] = useState({
    newMatches: true,
    messages: true,
    activities: true,
    gameInvites: true,
    emailNotifications: false
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await authAPI.getProfile();
      const userData = response.data.user;

      // Load current settings from user profile
      setPrivacySettings({
        showAge: userData.privacy?.showAge ?? true,
        showLocation: userData.privacy?.showLocation ?? true,
        showLastActive: userData.privacy?.showLastActive ?? true,
        allowMessages: userData.privacy?.allowMessages ?? true,
        visibleInSearch: userData.privacy?.visibleInSearch ?? true
      });

      setMatchPreferences({
        ageRange: userData.matchPreferences?.ageRange || { min: 18, max: 50 },
        maxDistance: userData.matchPreferences?.maxDistance || 50,
        genderPreference: userData.matchPreferences?.gender || 'all',
        mysteryMode: {
          enabled: userData.matchPreferences?.mysteryMode ?? true,
          revealSpeed: userData.matchPreferences?.revealSpeed || 'medium'
        }
      });

      setNotificationSettings({
        newMatches: userData.notifications?.newMatches ?? true,
        messages: userData.notifications?.messages ?? true,
        activities: userData.notifications?.activities ?? true,
        gameInvites: userData.notifications?.gameInvites ?? true,
        emailNotifications: userData.notifications?.emailNotifications ?? false
      });

      setAccountSettings(prev => ({
        ...prev,
        email: userData.email || ''
      }));
    } catch (error) {
      console.error('Load settings error:', error);
      showMessage('error', '加载设置失败');
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  const handleSaveSettings = async () => {
    try {
      setSaving(true);

      // Validate password change if provided
      if (accountSettings.newPassword) {
        if (!accountSettings.currentPassword) {
          showMessage('error', '请输入当前密码');
          return;
        }
        if (accountSettings.newPassword !== accountSettings.confirmPassword) {
          showMessage('error', '新密码不匹配');
          return;
        }
        if (accountSettings.newPassword.length < 6) {
          showMessage('error', '新密码至少需要6个字符');
          return;
        }
      }

      const updateData = {
        privacy: privacySettings,
        matchPreferences: {
          ...matchPreferences,
          gender: matchPreferences.genderPreference,
          mysteryMode: matchPreferences.mysteryMode.enabled,
          revealSpeed: matchPreferences.mysteryMode.revealSpeed
        },
        notifications: notificationSettings
      };

      // Add password change if provided
      if (accountSettings.newPassword) {
        updateData.currentPassword = accountSettings.currentPassword;
        updateData.newPassword = accountSettings.newPassword;
      }

      const response = await authAPI.updateProfile(updateData);
      setUser(response.data.user);

      showMessage('success', '设置已保存');

      // Clear password fields
      setAccountSettings(prev => ({
        ...prev,
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
      }));
    } catch (error) {
      console.error('Save settings error:', error);
      showMessage('error', error.response?.data?.error || '保存设置失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block w-16 h-16 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-gray-400 mt-4">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 p-6 pb-24">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-white mb-6 flex items-center gap-3">
          <Cog6ToothIcon className="w-8 h-8 text-purple-400" />
          设置
        </h1>

        {/* Message Display */}
        {message.text && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`mb-6 p-4 rounded-lg ${
              message.type === 'success'
                ? 'bg-green-500/20 border border-green-500/50 text-green-300'
                : 'bg-red-500/20 border border-red-500/50 text-red-300'
            }`}
          >
            {message.text}
          </motion.div>
        )}

        {/* Account Settings */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mystery-card p-6 mb-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <UserCircleIcon className="w-6 h-6 text-purple-400" />
            账户设置
          </h2>

          <div className="space-y-4">
            <div>
              <label className="text-gray-300 text-sm mb-2 block">邮箱</label>
              <input
                type="email"
                value={accountSettings.email}
                onChange={(e) => setAccountSettings(prev => ({ ...prev, email: e.target.value }))}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                disabled
              />
            </div>

            <div className="border-t border-white/10 pt-4">
              <h3 className="text-white font-semibold mb-3">修改密码</h3>
              <div className="space-y-3">
                <input
                  type="password"
                  placeholder="当前密码"
                  value={accountSettings.currentPassword}
                  onChange={(e) => setAccountSettings(prev => ({ ...prev, currentPassword: e.target.value }))}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <input
                  type="password"
                  placeholder="新密码"
                  value={accountSettings.newPassword}
                  onChange={(e) => setAccountSettings(prev => ({ ...prev, newPassword: e.target.value }))}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <input
                  type="password"
                  placeholder="确认新密码"
                  value={accountSettings.confirmPassword}
                  onChange={(e) => setAccountSettings(prev => ({ ...prev, confirmPassword: e.target.value }))}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
          </div>
        </motion.div>

        {/* Privacy Settings */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mystery-card p-6 mb-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <ShieldCheckIcon className="w-6 h-6 text-purple-400" />
            隐私设置
          </h2>

          <div className="space-y-4">
            {Object.entries({
              showAge: '显示年龄',
              showLocation: '显示位置',
              showLastActive: '显示最近活跃时间',
              allowMessages: '允许接收消息',
              visibleInSearch: '在搜索中可见'
            }).map(([key, label]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-gray-300">{label}</span>
                <button
                  onClick={() => setPrivacySettings(prev => ({ ...prev, [key]: !prev[key] }))}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    privacySettings[key] ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <motion.div
                    animate={{ x: privacySettings[key] ? 28 : 2 }}
                    className="absolute top-1 w-5 h-5 bg-white rounded-full"
                  />
                </button>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Match Preferences */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mystery-card p-6 mb-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <HeartIcon className="w-6 h-6 text-pink-400" />
            匹配偏好
          </h2>

          <div className="space-y-4">
            <div>
              <label className="text-gray-300 text-sm mb-2 block">年龄范围</label>
              <div className="flex items-center gap-4">
                <input
                  type="number"
                  min="18"
                  max="100"
                  value={matchPreferences.ageRange.min}
                  onChange={(e) => setMatchPreferences(prev => ({
                    ...prev,
                    ageRange: { ...prev.ageRange, min: parseInt(e.target.value) }
                  }))}
                  className="w-24 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <span className="text-gray-400">-</span>
                <input
                  type="number"
                  min="18"
                  max="100"
                  value={matchPreferences.ageRange.max}
                  onChange={(e) => setMatchPreferences(prev => ({
                    ...prev,
                    ageRange: { ...prev.ageRange, max: parseInt(e.target.value) }
                  }))}
                  className="w-24 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <span className="text-gray-400">岁</span>
              </div>
            </div>

            <div>
              <label className="text-gray-300 text-sm mb-2 block">最大距离</label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min="5"
                  max="500"
                  step="5"
                  value={matchPreferences.maxDistance}
                  onChange={(e) => setMatchPreferences(prev => ({
                    ...prev,
                    maxDistance: parseInt(e.target.value)
                  }))}
                  className="flex-1"
                />
                <span className="text-white font-semibold w-20">
                  {matchPreferences.maxDistance} km
                </span>
              </div>
            </div>

            <div>
              <label className="text-gray-300 text-sm mb-2 block">性别偏好</label>
              <select
                value={matchPreferences.genderPreference}
                onChange={(e) => setMatchPreferences(prev => ({
                  ...prev,
                  genderPreference: e.target.value
                }))}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="all">全部</option>
                <option value="male">男性</option>
                <option value="female">女性</option>
              </select>
            </div>

            <div className="border-t border-white/10 pt-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-gray-300">神秘模式</span>
                <button
                  onClick={() => setMatchPreferences(prev => ({
                    ...prev,
                    mysteryMode: { ...prev.mysteryMode, enabled: !prev.mysteryMode.enabled }
                  }))}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    matchPreferences.mysteryMode.enabled ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <motion.div
                    animate={{ x: matchPreferences.mysteryMode.enabled ? 28 : 2 }}
                    className="absolute top-1 w-5 h-5 bg-white rounded-full"
                  />
                </button>
              </div>

              {matchPreferences.mysteryMode.enabled && (
                <div>
                  <label className="text-gray-300 text-sm mb-2 block">信息揭示速度</label>
                  <select
                    value={matchPreferences.mysteryMode.revealSpeed}
                    onChange={(e) => setMatchPreferences(prev => ({
                      ...prev,
                      mysteryMode: { ...prev.mysteryMode, revealSpeed: e.target.value }
                    }))}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="slow">慢速（更神秘）</option>
                    <option value="medium">中速</option>
                    <option value="fast">快速</option>
                  </select>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* Notification Settings */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mystery-card p-6 mb-6"
        >
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <BellIcon className="w-6 h-6 text-yellow-400" />
            通知设置
          </h2>

          <div className="space-y-4">
            {Object.entries({
              newMatches: '新匹配通知',
              messages: '消息通知',
              activities: '活动通知',
              gameInvites: '游戏邀请通知',
              emailNotifications: '邮件通知'
            }).map(([key, label]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-gray-300">{label}</span>
                <button
                  onClick={() => setNotificationSettings(prev => ({ ...prev, [key]: !prev[key] }))}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    notificationSettings[key] ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <motion.div
                    animate={{ x: notificationSettings[key] ? 28 : 2 }}
                    className="absolute top-1 w-5 h-5 bg-white rounded-full"
                  />
                </button>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Save Button */}
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          onClick={handleSaveSettings}
          disabled={saving}
          className="w-full py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold rounded-lg hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? '保存中...' : '保存设置'}
        </motion.button>
      </div>
    </div>
  );
};

export default Settings;
