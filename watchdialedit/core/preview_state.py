import datetime
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PreviewState:
    hour: int = 10
    minute: int = 8
    second: int = 36
    year: int = 2026
    month: int = 9
    day: int = 23           # a Wednesday; JS default week index is 3 (Wed)
    bluetooth_connected: bool = True       # processDialStatus "bluetooth"
    redpoint_shown: bool = False           # processDialStatus "redpoint"
    daytime: bool = True                   # sunswitch frame select
    anima_frame: int = 0
    values: Dict[str, float] = field(default_factory=lambda: {
        "heartrate": 72, "calorie": 380, "distance": 6.08, "step": 6800,
        "battery": 98, "weather": 24})

    def weekday_sun0(self) -> int:
        """moment().format('e') in en locale: Sunday=0 .. Saturday=6."""
        d = datetime.date(self.year, self.month, self.day)
        return (d.weekday() + 1) % 7
