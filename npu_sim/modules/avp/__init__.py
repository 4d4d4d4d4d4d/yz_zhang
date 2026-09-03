"""AVP module: Activation & Vector Post-processor (timing + functional). SPEC-005 §5."""

from npu_sim.modules.avp.avp_module import AVP
from npu_sim.modules.avp.avp_numerical import AVPGoldenModel

__all__ = ["AVP", "AVPGoldenModel"]
