// Spec 60 — the `markets` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import MarketEntryScorer from '../../components/MarketEntryScorer.vue'
import LandedCostPricer from '../../components/LandedCostPricer.vue'
import MarketReadiness from '../../components/MarketReadiness.vue'
import RetailCalendar from '../../components/RetailCalendar.vue'

export default {
  entry: MarketEntryScorer,
  landed: LandedCostPricer,
  readiness: MarketReadiness,
  calendar: RetailCalendar,
}
