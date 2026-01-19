import express from 'express';
import { authenticate } from '../middleware/auth.js';
import {
  createPartyRoom,
  getActiveRooms,
  getRoomDetails,
  joinRoom,
  leaveRoom,
  takeSeat,
  leaveSeat,
  sendRoomMessage,
  toggleMute,
  endRoom
} from '../controllers/partyRoomController.js';

const router = express.Router();

// Room management
router.post('/', authenticate, createPartyRoom);
router.get('/active', authenticate, getActiveRooms);
router.get('/:roomId', authenticate, getRoomDetails);
router.post('/:roomId/join', authenticate, joinRoom);
router.post('/:roomId/leave', authenticate, leaveRoom);
router.post('/:roomId/end', authenticate, endRoom);

// Seat management
router.post('/:roomId/seat', authenticate, takeSeat);
router.delete('/:roomId/seat', authenticate, leaveSeat);

// Communication
router.post('/:roomId/message', authenticate, sendRoomMessage);
router.post('/:roomId/mute/:userId', authenticate, toggleMute);

export default router;
