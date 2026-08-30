// Spec 59 — the `deals` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import DealRoom from '../../components/DealRoom.vue'
import NegotiationPlaybook from '../../components/NegotiationPlaybook.vue'
import ApprovalFlow from '../../components/ApprovalFlow.vue'
import ClauseLibrary from '../../components/ClauseLibrary.vue'
import ObligationTracker from '../../components/ObligationTracker.vue'
import ContractAnalytics from '../../components/ContractAnalytics.vue'
import CPQEditor from '../../components/CPQEditor.vue'
import RevenueRecognition from '../../components/RevenueRecognition.vue'

export default {
  room: DealRoom,
  playbook: NegotiationPlaybook,
  workflow: ApprovalFlow,
  library: ClauseLibrary,
  obligations: ObligationTracker,
  analytics: ContractAnalytics,
  cpq: CPQEditor,
  revrec: RevenueRecognition,
}
