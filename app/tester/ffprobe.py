import asyncio,json
from dataclasses import dataclass
from app.core.config import get_settings
@dataclass
class FFProbeResult:
 ok:bool; raw:dict|None=None; video_codec:str|None=None; audio_codec:str|None=None; width:int|None=None; height:int|None=None; fps:float|None=None; bitrate:int|None=None; error_type:str|None=None; error_message:str|None=None
def _fps(v):
 try:
  a,b=v.split('/');return float(a)/float(b) if float(b) else None
 except Exception:return None
async def run_ffprobe(url,headers=None,semaphore=None):
 async def run():
  cmd=['ffprobe','-v','error','-print_format','json','-show_streams','-show_format']
  if headers:cmd+=['-headers',''.join(f'{k}: {v}\r\n' for k,v in headers.items())]
  cmd.append(url)
  try:
   p=await asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
   try:o,e=await asyncio.wait_for(p.communicate(),get_settings().ffprobe_timeout)
   except asyncio.TimeoutError:p.kill();await p.communicate();return FFProbeResult(False,error_type='TIMEOUT',error_message='ffprobe timeout')
   if p.returncode:return FFProbeResult(False,error_type='FFPROBE_ERROR',error_message=e.decode(errors='replace')[-1000:])
   raw=json.loads(o);ss=raw.get('streams',[]);v=next((x for x in ss if x.get('codec_type')=='video'),{});a=next((x for x in ss if x.get('codec_type')=='audio'),{});br=v.get('bit_rate') or raw.get('format',{}).get('bit_rate')
   return FFProbeResult(True,raw,v.get('codec_name'),a.get('codec_name'),v.get('width'),v.get('height'),_fps(v.get('avg_frame_rate') or v.get('r_frame_rate')),int(br) if br and str(br).isdigit() else None)
  except FileNotFoundError:return FFProbeResult(False,error_type='FFPROBE_UNAVAILABLE',error_message='ffprobe not installed')
  except Exception as e:return FFProbeResult(False,error_type='FFPROBE_ERROR',error_message=str(e))
 return await run() if semaphore is None else await _guard(semaphore,run)
async def _guard(s,f):
 async with s:return await f()
