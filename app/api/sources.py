from fastapi import APIRouter,Depends
from sqlalchemy import select
from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.models import SourceDB,TestResultDB
from app.services.statistics_service import history,summarize
router=APIRouter()
@router.get('/sources',dependencies=[Depends(require_admin)])
def sources():
 with SessionLocal() as s:return [{'id':x.id,'channel_id':x.channel_id,'url':x.url,'status':x.status,'enabled':x.enabled} for x in s.scalars(select(SourceDB))]
@router.get('/sources/{source_id}',dependencies=[Depends(require_admin)])
def source(source_id:int):
 with SessionLocal() as s:
  x=s.get(SourceDB,source_id);return {'id':x.id,'channel_id':x.channel_id,'url':x.url,'status':x.status,'enabled':x.enabled} if x else {'error':'not_found'}
@router.get('/sources/{source_id}/history',dependencies=[Depends(require_admin)])
def source_history(source_id:int,days:int=7):
 with SessionLocal() as s:
  rows=history(s,source_id,days);return {'summary':summarize(rows),'results':[{'id':r.id,'tested_at':r.tested_at.isoformat(),'score':r.score,'ttfb':r.ttfb,'speed':r.download_speed,'failure_rate':r.failure_rate} for r in rows]}
