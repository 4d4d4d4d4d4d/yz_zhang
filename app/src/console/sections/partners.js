// Spec 59 — the `partners` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import BusinessMatchHub from '../../components/BusinessMatchHub.vue'
import PipelineBoard from '../../components/PipelineBoard.vue'
import AccountIntel from '../../components/AccountIntel.vue'
import OutreachSequence from '../../components/OutreachSequence.vue'
import SalesForecast from '../../components/SalesForecast.vue'
import TerritoryQuota from '../../components/TerritoryQuota.vue'
import OrderBook from '../../components/OrderBook.vue'
import MarketplaceCommission from '../../components/MarketplaceCommission.vue'

export default {
  network: BusinessMatchHub,
  pipeline: PipelineBoard,
  intel: AccountIntel,
  outreach: OutreachSequence,
  forecast: SalesForecast,
  territory: TerritoryQuota,
  orders: OrderBook,
  commission: MarketplaceCommission,
}
