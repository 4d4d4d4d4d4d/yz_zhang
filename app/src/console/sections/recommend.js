// Spec 59 — the `recommend` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import RecommendDeep from '../../components/RecommendDeep.vue'
import RecommendAdvanced from '../../components/RecommendAdvanced.vue'
import ModelRegistry from '../../components/ModelRegistry.vue'
import BanditExplorer from '../../components/BanditExplorer.vue'
import FeatureStore from '../../components/FeatureStore.vue'
import ExperimentManager from '../../components/ExperimentManager.vue'
import UsageMetering from '../../components/UsageMetering.vue'
import PersonalizationDash from '../../components/PersonalizationDash.vue'

export default {
  inputs: RecommendDeep,
  agents: RecommendAdvanced,
  registry: ModelRegistry,
  bandit: BanditExplorer,
  features: FeatureStore,
  experiments: ExperimentManager,
  metering: UsageMetering,
  tenant: PersonalizationDash,
}
