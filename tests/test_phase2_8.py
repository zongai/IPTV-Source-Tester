import asyncio
from types import SimpleNamespace
from app.scoring.quality import calculate_score,resolution_label
from app.pool.source_pool import SourcePool
from app.pool.selector import select_best_source
from app.exporters.m3u import render_m3u
from app.tester.connectivity import classify_error

def test_score_and_resolution():
 assert resolution_label(1080)=='1080p';assert 0<=calculate_score(1,1,100,10,1080)<=100

def test_pool_failure_recovery():
 p=SourcePool(2);p.record_failure(1);assert p.get_status(1)=='active';p.record_failure(1);assert p.get_status(1)=='temporarily_failed';p.record_success(1);assert p.get_status(1)=='recovered'

def test_selector_prefers_resolution_when_requested():
 a=SimpleNamespace(status='active',enabled=True,height=720,score=99,speed=10,latency=10)
 b=SimpleNamespace(status='active',enabled=True,height=1080,score=80,speed=5,latency=20)
 assert select_best_source([a,b],min_resolution='1080p') is b

def test_exporter():
 x=render_m3u([{'name':'CCTV-1','url':'https://x/live','attrs':{'tvg-id':'cctv-1'},'headers':{'User-Agent':'X'}}])
 assert '#EXTM3U' in x and '#EXTVLCOPT:http-user-agent=X' in x

def test_error_categories():
 assert classify_error(asyncio.TimeoutError())=='TIMEOUT'
