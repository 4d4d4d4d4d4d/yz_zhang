// Spec 59 — the `marketing` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import MarketingHub from '../../components/MarketingHub.vue'
import MarketingControl from '../../components/MarketingControl.vue'
import AttributionWaterfall from '../../components/AttributionWaterfall.vue'
import AudienceBuilder from '../../components/AudienceBuilder.vue'
import CohortRetention from '../../components/CohortRetention.vue'
import ForecastSim from '../../components/ForecastSim.vue'
import RevenueDashboard from '../../components/RevenueDashboard.vue'
import UpsellEngine from '../../components/UpsellEngine.vue'
import FunnelView from '../../components/FunnelView.vue'

export default {
  overview: MarketingHub,
  control: MarketingControl,
  attribution: AttributionWaterfall,
  audience: AudienceBuilder,
  retention: CohortRetention,
  forecast: ForecastSim,
  revenue: RevenueDashboard,
  upsell: UpsellEngine,
  funnel: FunnelView,
}
