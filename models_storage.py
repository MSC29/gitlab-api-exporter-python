from dataclasses import dataclass
from datetime import datetime


@dataclass
class FloatScoreModel:
    time: datetime
    project_id: str
    project_name: str
    metric: str
    score: float
