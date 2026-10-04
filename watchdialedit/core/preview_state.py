"""Editor-only preview inputs (NOT part of iwf.json).

In the JS these are the per-widget `config.yl` fields. Time 10:08:36 is the value the
project owner verified for the IDW13 reference; the JS itself has no fixed time (it uses
`config.yl` or the wall clock). Other sample values are arbitrary editor defaults."""
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
    anima_frame: int = 0
    values: Dict[str, float] = field(default_factory=lambda: {
        "heartrate": 72, "calorie": 380, "distance": 6.08, "step": 6800,
        "battery": 98, "weather": 24})

    def weekday_sun0(self) -> int:
        """moment().format('e') in en locale: Sunday=0 .. Saturday=6."""
        d = datetime.date(self.year, self.month, self.day)
        return (d.weekday() + 1) % 7
