"""Device table.

The supplied JavaScript contains NO device configuration table (no IDW13/IDW16/...
constants; only the *name* of a store field `IDWDeviceIdArr`, whose contents are not
in the supplied source). Therefore only values proven by the real w552 fixture are
listed. Everything else is UNKNOWN - DO NOT GUESS.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Device:
    device_id: str
    width: int
    height: int
    source: str
    anchor_x: Optional[int] = None
    anchor_y: Optional[int] = None


VERIFIED_DEVICES = {
    "IDW13": Device("IDW13", 240, 284, "fixture w552", 120, 142),
    "IDW18": Device("IDW18", 240, 240, "requested from users", 120, 120),
    "IDW20": Device("IDW20", 320, 385, "user-provided", 160, 193),
}

# Deliberately no guesses; these need a real fixture / source table.
UNKNOWN_DEVICES = ["IDW16", "IDW17", "IDW26", "GTX03", "GTX10", "GTX13"]


def get_device(device_id: str) -> Optional[Device]:
    return VERIFIED_DEVICES.get(str(device_id).replace(" ", "").upper())
