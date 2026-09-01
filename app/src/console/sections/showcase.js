// Spec 59 — the `showcase` console section, shipped as one chunk.
// Shape: sub-tab key -> panel component. The keys must match SECTIONS
// in ../registry.js; tests/consolePanels.test.js enforces that both ways.

import ShowcaseGallery from '../../components/ShowcaseGallery.vue'
import TrustLinkBuilder from '../../components/TrustLinkBuilder.vue'
import VerificationQueue from '../../components/VerificationQueue.vue'
import TrustPipeline from '../../components/TrustPipeline.vue'
import DealReportCard from '../../components/DealReportCard.vue'

export default {
  gallery: ShowcaseGallery,
  links: TrustLinkBuilder,
  verification: VerificationQueue,
  pipeline: TrustPipeline,
  report: DealReportCard,
}
