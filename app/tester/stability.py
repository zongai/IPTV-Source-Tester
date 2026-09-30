import asyncio,time
from dataclasses import dataclass
from app.tester.hls import check_hls
@dataclass
class StabilityResult: attempts:int; successes:int; availability:float; failure_rate:float; average_latency:float|None
async def run_stability(url,session,duration=60,interval=2,headers=None):
 end=time.monotonic()+duration;n=ok=0;lat=[]
 while time.monotonic()<end:
  n+=1;t=time.perf_counter();r=await check_hls(url,session,1,headers)
  if r.valid:ok+=1;lat.append(time.perf_counter()-t)
  await asyncio.sleep(max(0,min(interval,end-time.monotonic())))
 a=ok/n if n else 0;return StabilityResult(n,ok,a,1-a,sum(lat)/len(lat) if lat else None)
