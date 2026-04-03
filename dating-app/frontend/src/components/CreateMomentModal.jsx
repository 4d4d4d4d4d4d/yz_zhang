import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { momentAPI } from '../services/api';
import {
  XMarkIcon,
  PhotoIcon,
  FaceSmileIcon,
  MapPinIcon,
  GlobeAltIcon,
  UserGroupIcon,
  LockClosedIcon,
  ChartBarIcon
} from '@heroicons/react/24/outline';

const CreateMomentModal = ({ isOpen, onClose, onSuccess }) => {
  const [content, setContent] = useState({ text: '', images: [] });
  const [type, setType] = useState('text');
  const [mood, setMood] = useState(null);
  const [visibility, setVisibility] = useState('public');
  const [anonymous, setAnonymous] = useState(false);
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);

  // Poll state
  const [pollQuestion, setPollQuestion] = useState('');
  const [pollOptions, setPollOptions] = useState(['', '']);

  const moods = [
    { emoji: '😊', label: '开心', color: '#FFD93D' },
    { emoji: '😢', label: '难过', color: '#6BCB77' },
    { emoji: '😡', label: '生气', color: '#FF6B6B' },
    { emoji: '😴', label: '困倦', color: '#4D96FF' },
    { emoji: '🤔', label: '思考', color: '#A8E6CF' },
    { emoji: '😎', label: '酷炫', color: '#FFD93D' },
    { emoji: '🥰', label: '恋爱', color: '#FF8DC7' },
    { emoji: '😱', label: '惊讶', color: '#FFA07A' }
  ];

  const visibilityOptions = [
    { value: 'public', label: '公开', icon: GlobeAltIcon, desc: '所有人可见' },
    { value: 'friends', label: '好友', icon: UserGroupIcon, desc: '仅好友可见' },
    { value: 'matches', label: '匹配', icon: '💕', desc: '仅匹配用户可见' },
    { value: 'private', label: '私密', icon: LockClosedIcon, desc: '仅自己可见' }
  ];

  const handleImageUpload = (e) => {
    const files = Array.from(e.target.files);
    // In production, upload to cloud storage and get URLs
    const imageUrls = files.map(file => URL.createObjectURL(file));
    setContent(prev => ({ ...prev, images: [...prev.images, ...imageUrls] }));
  };

  const handleSubmit = async () => {
    if (type === 'poll' && (!pollQuestion || pollOptions.filter(o => o.trim()).length < 2)) {
      alert('投票需要至少填写问题和2个选项');
      return;
    }

    if (type !== 'poll' && !content.text && content.images.length === 0) {
      alert('请输入内容或上传图片');
      return;
    }

    try {
      setLoading(true);

      const momentData = {
        content: type === 'poll' ? { text: pollQuestion } : content,
        type,
        mood,
        visibility,
        anonymous,
        tags: tags.split(',').map(t => t.trim()).filter(t => t),
        topics: tags.split(',').map(t => t.trim()).filter(t => t)
      };

      if (type === 'poll') {
        momentData.poll = {
          question: pollQuestion,
          options: pollOptions.filter(o => o.trim()).map(text => ({ text, votes: [] })),
          multipleChoice: false
        };
      }

      await momentAPI.createMoment(momentData);

      // Reset form
      setContent({ text: '', images: [] });
      setType('text');
      setMood(null);
      setTags('');
      setPollQuestion('');
      setPollOptions(['', '']);
      setAnonymous(false);

      if (onSuccess) onSuccess();
      onClose();
    } catch (error) {
      console.error('Create moment error:', error);
      alert(error.response?.data?.error || '发布失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="mystery-card w-full max-w-2xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h2 className="text-2xl font-bold text-white">发布瞬间</h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Type Selector */}
              <div className="flex gap-2">
                <button
                  onClick={() => setType('text')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    type === 'text'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  文字
                </button>
                <button
                  onClick={() => setType('image')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    type === 'image'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  图片
                </button>
                <button
                  onClick={() => setType('poll')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    type === 'poll'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  投票
                </button>
              </div>

              {/* Content Input */}
              {type !== 'poll' && (
                <textarea
                  value={content.text}
                  onChange={(e) => setContent(prev => ({ ...prev, text: e.target.value }))}
                  placeholder="分享此刻的想法..."
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                  rows={6}
                />
              )}

              {/* Poll Input */}
              {type === 'poll' && (
                <div className="space-y-4">
                  <input
                    value={pollQuestion}
                    onChange={(e) => setPollQuestion(e.target.value)}
                    placeholder="投票问题"
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  {pollOptions.map((option, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input
                        value={option}
                        onChange={(e) => {
                          const newOptions = [...pollOptions];
                          newOptions[idx] = e.target.value;
                          setPollOptions(newOptions);
                        }}
                        placeholder={`选项 ${idx + 1}`}
                        className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      {idx > 1 && (
                        <button
                          onClick={() => setPollOptions(pollOptions.filter((_, i) => i !== idx))}
                          className="px-3 text-red-400 hover:text-red-300"
                        >
                          删除
                        </button>
                      )}
                    </div>
                  ))}
                  {pollOptions.length < 6 && (
                    <button
                      onClick={() => setPollOptions([...pollOptions, ''])}
                      className="w-full px-4 py-2 bg-white/10 text-gray-300 rounded-lg hover:bg-white/20 transition-all"
                    >
                      + 添加选项
                    </button>
                  )}
                </div>
              )}

              {/* Image Upload */}
              {(type === 'image' || type === 'text') && (
                <div>
                  <label className="flex items-center gap-2 px-4 py-3 bg-white/10 rounded-lg hover:bg-white/20 transition-all cursor-pointer">
                    <PhotoIcon className="w-5 h-5 text-purple-400" />
                    <span className="text-gray-300">上传图片</span>
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      onChange={handleImageUpload}
                      className="hidden"
                    />
                  </label>

                  {content.images.length > 0 && (
                    <div className="grid grid-cols-3 gap-2 mt-4">
                      {content.images.map((img, idx) => (
                        <div key={idx} className="relative">
                          <img
                            src={img}
                            alt="upload"
                            className="w-full h-32 object-cover rounded-lg"
                          />
                          <button
                            onClick={() => setContent(prev => ({
                              ...prev,
                              images: prev.images.filter((_, i) => i !== idx)
                            }))}
                            className="absolute top-1 right-1 w-6 h-6 bg-red-500 rounded-full flex items-center justify-center text-white"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Mood Selector */}
              <div>
                <label className="text-gray-300 text-sm mb-2 block flex items-center gap-2">
                  <FaceSmileIcon className="w-5 h-5" />
                  心情
                </label>
                <div className="flex flex-wrap gap-2">
                  {moods.map((m) => (
                    <button
                      key={m.label}
                      onClick={() => setMood(mood?.label === m.label ? null : m)}
                      className={`px-4 py-2 rounded-lg transition-all ${
                        mood?.label === m.label
                          ? 'bg-purple-600 text-white scale-110'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      <span className="text-xl mr-2">{m.emoji}</span>
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tags */}
              <div>
                <label className="text-gray-300 text-sm mb-2 block">话题标签（用逗号分隔）</label>
                <input
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="例如：旅行,美食,心情"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              {/* Visibility */}
              <div>
                <label className="text-gray-300 text-sm mb-2 block">可见范围</label>
                <div className="grid grid-cols-2 gap-3">
                  {visibilityOptions.map((option) => {
                    const Icon = typeof option.icon === 'string' ? null : option.icon;
                    return (
                      <button
                        key={option.value}
                        onClick={() => setVisibility(option.value)}
                        className={`p-3 rounded-lg text-left transition-all ${
                          visibility === option.value
                            ? 'bg-purple-600 border-2 border-purple-400'
                            : 'bg-white/10 border-2 border-transparent hover:bg-white/20'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          {Icon ? (
                            <Icon className="w-5 h-5" />
                          ) : (
                            <span className="text-xl">{option.icon}</span>
                          )}
                          <span className="text-white font-semibold">{option.label}</span>
                        </div>
                        <p className="text-gray-400 text-xs">{option.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Anonymous Toggle */}
              <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg">
                <div>
                  <h3 className="text-white font-semibold">匿名发布</h3>
                  <p className="text-gray-400 text-sm">隐藏你的身份信息</p>
                </div>
                <button
                  onClick={() => setAnonymous(!anonymous)}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    anonymous ? 'bg-purple-600' : 'bg-gray-600'
                  }`}
                >
                  <motion.div
                    animate={{ x: anonymous ? 28 : 2 }}
                    className="absolute top-1 w-5 h-5 bg-white rounded-full"
                  />
                </button>
              </div>
            </div>

            {/* Footer */}
            <div className="flex gap-3 p-6 border-t border-white/10">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="flex-1 px-4 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg hover:shadow-lg transition-all disabled:opacity-50"
              >
                {loading ? '发布中...' : '发布瞬间'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default CreateMomentModal;
