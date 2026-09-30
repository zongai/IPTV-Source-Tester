def rank_sources(sources,strategy='balanced'):
 def k(s):
  g=lambda n,d=0:getattr(s,n,s.get(n,d) if isinstance(s,dict) else d)
  score=g('score');speed=g('speed',g('download_speed'));lat=g('latency',999999);height=g('height',0)
  return {'best_quality':(score,),'best_speed':(speed,),'lowest_latency':(-lat,),'highest_resolution':(height,score)}.get(strategy,(score,speed,-lat,height))
 return sorted(sources,key=k,reverse=True)
