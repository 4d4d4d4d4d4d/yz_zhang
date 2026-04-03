import Notification from '../models/Notification.js';

/**
 * 获取我的通知列表
 */
export const getMyNotifications = async (req, res) => {
  try {
    const { page = 1, limit = 20, unreadOnly = false } = req.query;

    const query = { recipient: req.userId };
    if (unreadOnly === 'true') {
      query.isRead = false;
    }

    const notifications = await Notification.find(query)
      .populate('sender', 'username profile.displayName profile.photos')
      .sort({ createdAt: -1 })
      .limit(parseInt(limit))
      .skip((parseInt(page) - 1) * parseInt(limit));

    const total = await Notification.countDocuments(query);
    const unreadCount = await Notification.getUnreadCount(req.userId);

    res.json({
      notifications,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        pages: Math.ceil(total / parseInt(limit))
      },
      unreadCount
    });
  } catch (error) {
    console.error('Get Notifications Error:', error);
    res.status(500).json({ error: 'Failed to get notifications' });
  }
};

/**
 * 获取未读通知数量
 */
export const getUnreadCount = async (req, res) => {
  try {
    const count = await Notification.getUnreadCount(req.userId);
    res.json({ count });
  } catch (error) {
    console.error('Get Unread Count Error:', error);
    res.status(500).json({ error: 'Failed to get unread count' });
  }
};

/**
 * 标记通知为已读
 */
export const markAsRead = async (req, res) => {
  try {
    const { notificationId } = req.params;

    const notification = await Notification.findById(notificationId);
    if (!notification) {
      return res.status(404).json({ error: 'Notification not found' });
    }

    // 检查是否是接收者
    if (notification.recipient.toString() !== req.userId.toString()) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    notification.markAsRead();
    await notification.save();

    res.json({
      message: 'Notification marked as read',
      notification
    });
  } catch (error) {
    console.error('Mark As Read Error:', error);
    res.status(500).json({ error: 'Failed to mark notification as read' });
  }
};

/**
 * 标记所有通知为已读
 */
export const markAllAsRead = async (req, res) => {
  try {
    const result = await Notification.markAllAsRead(req.userId);

    res.json({
      message: 'All notifications marked as read',
      count: result.modifiedCount
    });
  } catch (error) {
    console.error('Mark All As Read Error:', error);
    res.status(500).json({ error: 'Failed to mark all as read' });
  }
};

/**
 * 删除通知
 */
export const deleteNotification = async (req, res) => {
  try {
    const { notificationId } = req.params;

    const notification = await Notification.findById(notificationId);
    if (!notification) {
      return res.status(404).json({ error: 'Notification not found' });
    }

    // 检查是否是接收者
    if (notification.recipient.toString() !== req.userId.toString()) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    await notification.deleteOne();

    res.json({ message: 'Notification deleted' });
  } catch (error) {
    console.error('Delete Notification Error:', error);
    res.status(500).json({ error: 'Failed to delete notification' });
  }
};

/**
 * 清空所有已读通知
 */
export const clearReadNotifications = async (req, res) => {
  try {
    const result = await Notification.deleteMany({
      recipient: req.userId,
      isRead: true
    });

    res.json({
      message: 'Read notifications cleared',
      count: result.deletedCount
    });
  } catch (error) {
    console.error('Clear Read Notifications Error:', error);
    res.status(500).json({ error: 'Failed to clear notifications' });
  }
};

/**
 * 辅助函数：创建通知
 */
export const createNotification = async (data) => {
  try {
    return await Notification.createNotification(data);
  } catch (error) {
    console.error('Create Notification Error:', error);
    throw error;
  }
};

/**
 * 辅助函数：批量创建通知
 */
export const createBulkNotifications = async (recipients, notificationData) => {
  try {
    const notifications = recipients.map(recipientId => ({
      ...notificationData,
      recipient: recipientId
    }));

    return await Notification.insertMany(notifications);
  } catch (error) {
    console.error('Create Bulk Notifications Error:', error);
    throw error;
  }
};
