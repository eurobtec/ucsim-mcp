import os
import shutil

import pytest

UCSIM_BINARY = os.environ.get(
    "UCSIM_BINARY",
    os.path.expanduser("~/github/razr/ucsim/src/sims/s51.src/ucsim_51"),
)
ROB3_ROM = os.path.expanduser(
    "~/github/razr/rob3/firmware/hex/M2764A@DIP28.HEX")


def _binary_available() -> bool:
    return bool(shutil.which(UCSIM_BINARY) or os.path.exists(UCSIM_BINARY))


requires_binary = pytest.mark.skipif(
    not _binary_available(),
    reason=f"ucSim binary not available at {UCSIM_BINARY}",
)

requires_rom = pytest.mark.skipif(
    not os.path.exists(ROB3_ROM),
    reason="ROB3 test ROM not available",
)
