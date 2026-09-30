from dataclasses import dataclass
@dataclass
class PoolState: failures:int=0; status:str='active'
class SourcePool:
 def __init__(self,max_failures=3):self.max_failures=max_failures;self.states={}
 def record_success(self,i):
  s=self.states.setdefault(i,PoolState());s.failures=0;s.status='recovered' if s.status=='temporarily_failed' else 'active';return s
 def record_failure(self,i):
  s=self.states.setdefault(i,PoolState());s.failures+=1
  if s.failures>=self.max_failures:s.status='temporarily_failed'
  return s
 def get_status(self,i):return self.states.setdefault(i,PoolState()).status
