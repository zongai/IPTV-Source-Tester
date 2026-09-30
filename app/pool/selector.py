from app.scoring.ranking import rank_sources
H={'SD':480,'480p':480,'720p':720,'1080p':1080,'2K':1440,'4K':2160}
def select_best_source(sources,strategy='balanced',min_resolution=None):
 u=[s for s in sources if getattr(s,'status','active') not in {'temporarily_failed','inactive'} and getattr(s,'enabled',True)]
 if min_resolution:
  t=H.get(min_resolution,min_resolution if isinstance(min_resolution,int) else 0);x=[s for s in u if (getattr(s,'height',0) or 0)>=t];u=x or u
 r=rank_sources(u,strategy);return r[0] if r else None
def get_sources(sources,strategy='balanced'):return rank_sources(sources,strategy)
