from dataclasses import dataclass
@dataclass
class SpeedStats: average:float; minimum:float; maximum:float
def summarize(speeds):return None if not speeds else SpeedStats(sum(speeds)/len(speeds),min(speeds),max(speeds))
