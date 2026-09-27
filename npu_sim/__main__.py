"""Allow `python -m npu_sim` to dispatch through the CLI."""

import sys

from npu_sim.cli import main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
