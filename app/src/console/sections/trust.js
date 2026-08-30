// Spec 59 — the `trust` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import TrustCenter from '../../components/TrustCenter.vue'
import ControlsRegister from '../../components/ControlsRegister.vue'
import RiskHeatmap from '../../components/RiskHeatmap.vue'
import DPIAWorkflow from '../../components/DPIAWorkflow.vue'
import AuditRoom from '../../components/AuditRoom.vue'
import PolicyManagement from '../../components/PolicyManagement.vue'
import CustomerHealth from '../../components/CustomerHealth.vue'
import SupportSLA from '../../components/SupportSLA.vue'

export default {
  posture: TrustCenter,
  controls: ControlsRegister,
  heatmap: RiskHeatmap,
  dpia: DPIAWorkflow,
  audit: AuditRoom,
  policies: PolicyManagement,
  health: CustomerHealth,
  support: SupportSLA,
}
