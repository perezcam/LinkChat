from dataclasses import dataclass, field
import time
from typing import Callable

@dataclass
class ScheduledTask:
    action: Callable[[], None]  
    interval: float             
    last_run: float = field(default_factory=time.time) 