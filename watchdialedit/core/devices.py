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
    # Confirmed watch-hand anchor point (houranchorx/y etc.) for a full-canvas watch
    # item on this device. NOT always floor(width/2), floor(height/2) - e.g. IDW20's
    # height (385) is odd and its real anchor rounds up, not down. None means
    # unconfirmed; callers fall back to floor division in that case.
    anchor_x: Optional[int] = None
    anchor_y: Optional[int] = None


# IDW13: 240x284 - proven by w552/iwf.json (bkground files129.bmp is 240x284 and the
# full-screen 'watch' widget is w=240,h=284, deviceId "IDW13"; anchors 120,142 are the
# fixture's real houranchorx/houranchory, which happen to equal floor(w/2), floor(h/2)).
# IDW20: 320x385, anchor 160,193 - user-provided; NOT floor(385/2)=192, so stored
# explicitly rather than derived.
VERIFIED_DEVICES = {
    "IDW13": Device("IDW13", 240, 284, "fixture w552", 120, 142),
    "IDW20": Device("IDW20", 320, 385, "user-provided", 160, 193),
}

# Deliberately no guesses; these need a real fixture / source table.
UNKNOWN_DEVICES = ["IDW16", "IDW17", "IDW18", "IDW26", "GTX03", "GTX10", "GTX13"]


def get_device(device_id: str) -> Optional[Device]:
    return VERIFIED_DEVICES.get(str(device_id).replace(" ", "").upper())