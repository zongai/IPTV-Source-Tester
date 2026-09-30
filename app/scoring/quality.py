def resolution_label(h):
 if not h:return None
 return '4K' if h>=2160 else '2K' if h>=1440 else '1080p' if h>=1080 else '720p' if h>=720 else '480p' if h>=480 else 'SD'
def calculate_score(availability=0,stability=0,latency_ms=None,speed_mbps=None,height=None,startup_s=None):
 a=max(0,min(1,availability))*30;s=max(0,min(1,stability))*25
 l=15 if latency_ms is None else max(0,min(15,15/(1+latency_ms/250)))
 b=15 if (speed_mbps or 0)>=20 else 13 if (speed_mbps or 0)>=10 else 10 if (speed_mbps or 0)>=5 else 7 if (speed_mbps or 0)>=2.5 else 4 if (speed_mbps or 0)>=1 else 0
 r=10 if (height or 0)>=2160 else 9 if (height or 0)>=1440 else 8 if (height or 0)>=1080 else 6 if (height or 0)>=720 else 4 if (height or 0)>=480 else 0
 st=5 if startup_s is None else max(0,min(5,5/(1+startup_s/2)))
 return round(max(0,min(100,a+s+l+b+r+st)),2)
