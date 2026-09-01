// Spec 59 — the `immersive` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import AvatarStudio from '../../components/AvatarStudio.vue'
import ImmersiveMeeting from '../../components/ImmersiveMeeting.vue'
import MeetingPlanner from '../../components/MeetingPlanner.vue'
import VirtualTour from '../../components/VirtualTour.vue'
import FieldVerification from '../../components/FieldVerification.vue'

export default {
  avatar: AvatarStudio,
  meeting: ImmersiveMeeting,
  planner: MeetingPlanner,
  tour: VirtualTour,
  field: FieldVerification,
}
