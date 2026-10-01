import asyncio
from datetime import datetime, timedelta
from sqlalchemy import delete, select, text
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import get_settings
from app.database.database import SessionLocal
from app.database.locks import db_write_lock
from app.database.models import SourceDB, TestResultDB, SchedulerConfigDB, SchedulerRunDB, RemotePlaylistDB
from app.database.repository import maybe_auto_delete_failed_source, retain_ffprobe_media_fields
from app.services.remote_playlist_service import fetch_remote_playlist
from app.services.test_service import TestRunner
from app.utils.timeutil import app_timezone


class SchedulerService:
    def __init__(self):
        # Use container TZ so next_run_at aligns with local wall clock.
        self.scheduler = AsyncIOScheduler(timezone=app_timezone())
        self._running_job: asyncio.Task | None = None
        self._run_lock = asyncio.Lock()
        self.job_id = "iptv-periodic-test"

    def _ensure_schema(self, session):
        if session.bind.dialect.name != 'sqlite':
            return
        cols = {row[1] for row in session.execute(text('PRAGMA table_info(scheduler_config)'))}
        additions = {
            'max_concurrency': 'INTEGER DEFAULT 20',
            'max_host_concurrency': 'INTEGER DEFAULT 1',
            'connect_timeout': 'INTEGER DEFAULT 5',
            'read_timeout': 'INTEGER DEFAULT 10',
            'segment_test_count': 'INTEGER DEFAULT 2',
            'full_enabled': 'INTEGER DEFAULT 0',
            'full_interval_hours': 'INTEGER DEFAULT 24',
        }
        for name, definition in additions.items():
            if name not in cols:
                session.execute(text(f'ALTER TABLE scheduler_config ADD COLUMN {name} {definition}'))
        session.commit()

    def _config(self, session):
        self._ensure_schema(session)
        cfg = session.get(SchedulerConfigDB, 1)
        if cfg is None:
            s = get_settings()
            cfg = SchedulerConfigDB(
                id=1, enabled=True, interval_minutes=s.test_interval_minutes,
                # Lightweight: standard mode on stale sources only.
                test_mode="standard", source_scope="stale", stale_hours=24,
                max_concurrency=min(max(1, s.max_concurrency), 20),
                max_host_concurrency=max(1, min(s.max_host_concurrency, 1)),
                connect_timeout=max(1, int(s.connect_timeout)),
                read_timeout=max(1, int(s.read_timeout)),
                segment_test_count=max(1, min(s.segment_test_count, 2)),
                full_enabled=bool(s.full_test_enabled),
                full_interval_hours=max(1, int(s.full_test_interval_hours)),
            )
            session.add(cfg)
            session.commit()
            session.refresh(cfg)
        return cfg

    async def start(self):
        with SessionLocal() as session:
            cfg = self._config(session)
            enabled = cfg.enabled
            interval = cfg.interval_minutes
        if enabled:
            self._schedule(interval)
        with SessionLocal() as session:
            cfg2 = self._config(session)
            full_on = bool(getattr(cfg2, 'full_enabled', False))
            full_hours = max(1, int(getattr(cfg2, 'full_interval_hours', 24) or 24))
            remote_playlists = list(session.scalars(select(RemotePlaylistDB)).all())
        for playlist in remote_playlists:
            self.schedule_remote_playlist(playlist.id, playlist.interval_minutes, playlist.enabled)
        # Periodic history cleanup (startup also runs once in app lifespan).
        self.scheduler.add_job(
            self._cleanup_history,
            "interval",
            hours=24,
            id="iptv-history-cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        self._schedule_full(full_on, full_hours)

    async def _cleanup_history(self):
        from app.database.maintenance import cleanup_old_test_results

        async with db_write_lock:
            await asyncio.to_thread(cleanup_old_test_results)

    def _schedule(self, minutes: int):
        self.scheduler.add_job(
            self._schedule_run, 'interval', minutes=max(1, int(minutes)), id=self.job_id,
            replace_existing=True, max_instances=1, coalesce=True,
        )

    full_job_id = "iptv-periodic-full"

    def _schedule_full(self, enabled: bool, hours: int):
        if not self.scheduler.running and not enabled:
            # scheduler not started yet; start() will call again after start
            pass
        if not enabled:
            if self.scheduler.running and self.scheduler.get_job(self.full_job_id):
                self.scheduler.remove_job(self.full_job_id)
            return
        self.scheduler.add_job(
            self._schedule_full_run,
            'interval',
            hours=max(1, int(hours)),
            id=self.full_job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def _schedule_full_run(self):
        if self._running_job and not self._running_job.done():
            return
        self._running_job = asyncio.create_task(
            self.run_now(trigger="scheduled_full", mode_override="full", scope_override="stale")
        )
        try:
            await self._running_job
        except asyncio.CancelledError:
            pass
        finally:
            self._running_job = None

    def _remote_job_id(self, playlist_id: int) -> str:
        return f"iptv-remote-playlist-{playlist_id}"

    def schedule_remote_playlist(self, playlist_id: int, minutes: int, enabled: bool = True):
        job_id = self._remote_job_id(playlist_id)
        if not enabled:
            if self.scheduler.running and self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            return
        self.scheduler.add_job(
            self._remote_playlist_job, 'interval', minutes=max(1, int(minutes)),
            args=[playlist_id], id=job_id, replace_existing=True,
            max_instances=1, coalesce=True,
        )

    def unschedule_remote_playlist(self, playlist_id: int):
        job_id = self._remote_job_id(playlist_id)
        if self.scheduler.running and self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def _remote_playlist_job(self, playlist_id: int):
        with SessionLocal() as session:
            playlist = session.get(RemotePlaylistDB, playlist_id)
            if not playlist or not playlist.enabled:
                return
        try:
            result = await fetch_remote_playlist(playlist_id)
            if result.get("auto_deleted"):
                self.unschedule_remote_playlist(playlist_id)
        except Exception:
            pass

    async def fetch_remote_playlist_now(self, playlist_id: int):
        result = await fetch_remote_playlist(playlist_id)
        if result.get("auto_deleted"):
            self.unschedule_remote_playlist(playlist_id)
            return result
        with SessionLocal() as session:
            playlist = session.get(RemotePlaylistDB, playlist_id)
            if playlist:
                self.schedule_remote_playlist(playlist.id, playlist.interval_minutes, playlist.enabled)
        return result

    async def stop(self):
        if self._running_job and not self._running_job.done():
            self._running_job.cancel()
            await asyncio.gather(self._running_job, return_exceptions=True)
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _schedule_run(self):
        if self._running_job and not self._running_job.done():
            return
        self._running_job = asyncio.create_task(self.run_now(trigger="scheduled"))
        try:
            await self._running_job
        except asyncio.CancelledError:
            pass
        finally:
            self._running_job = None

    async def run_now(self, trigger: str = "manual", mode_override: str | None = None, scope_override: str | None = None):
        if self._run_lock.locked():
            return {'status': 'already_running'}
        async with self._run_lock:
            return await self._run_now_locked(trigger=trigger, mode_override=mode_override, scope_override=scope_override)

    async def _run_now_locked(self, trigger: str = "manual", mode_override: str | None = None, scope_override: str | None = None):
        started_at = datetime.utcnow()
        with SessionLocal() as session:
            cfg = self._config(session)
            cfg.last_started_at = started_at
            cfg.last_status = 'running'
            session.commit()
            sources = list(session.scalars(select(SourceDB).where(SourceDB.enabled.is_(True))))
            scope = scope_override or cfg.source_scope
            if scope == 'failed':
                sources = [x for x in sources if x.status != 'active']
            elif scope == 'stale':
                cutoff = datetime.utcnow() - timedelta(hours=max(1, cfg.stale_hours))
                filtered = []
                for src in sources:
                    latest = session.scalar(
                        select(TestResultDB.tested_at)
                        .where(TestResultDB.source_id == src.id)
                        .order_by(TestResultDB.tested_at.desc())
                        .limit(1)
                    )
                    if latest is None or latest < cutoff:
                        filtered.append(src)
                sources = filtered
            mode = mode_override or cfg.test_mode
            max_concurrency = cfg.max_concurrency
            max_host_concurrency = cfg.max_host_concurrency
            connect_timeout = cfg.connect_timeout
            read_timeout = cfg.read_timeout
            segment_test_count = cfg.segment_test_count
            run_scope = scope

        with SessionLocal() as session:
            run = SchedulerRunDB(
                started_at=started_at, status="running", trigger=trigger,
                test_mode=mode, source_scope=run_scope, total=len(sources),
                tested=0, passed=0, failed=0,
            )
            session.add(run)
            session.commit()
            run_id = run.id
            # Keep the history bounded so long-running NAS instances do not grow the
            # scheduler history table indefinitely.  The newest 100 runs are retained.
            old_ids = session.scalars(
                select(SchedulerRunDB.id).order_by(SchedulerRunDB.started_at.desc()).offset(100)
            ).all()
            if old_ids:
                session.execute(delete(SchedulerRunDB).where(SchedulerRunDB.id.in_(old_ids)))
                session.commit()

        s = get_settings()
        runner = TestRunner(
            max_concurrency=max_concurrency,
            max_host_concurrency=max_host_concurrency,
            ffprobe_concurrency=s.ffprobe_concurrency,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            segment_test_count=segment_test_count,
            host_cooldown_seconds=s.host_cooldown_seconds,
        )
        saved = failed = 0
        fields = (
            'dns_latency','ttfb','http_status','content_type','playlist_valid',
            'segment_valid','video_codec','audio_codec','width','height','fps',
            'bitrate','download_speed','min_speed','max_speed','startup_time',
            'stability','failure_rate','score','error_type','error_message','ffprobe_json'
        )

        async def save_result(index, src, result):
            nonlocal saved, failed
            if isinstance(result, Exception):
                result = {'segment_valid': False, 'playlist_valid': False,
                          'error_type': 'INTERNAL_ERROR', 'error_message': str(result)[:1000]}
            try:
                async with db_write_lock:
                    with SessionLocal() as session:
                        # Carry forward last FFprobe resolution when this mode cannot measure it.
                        if isinstance(result, dict):
                            result = retain_ffprobe_media_fields(session, src.id, result)
                        session.add(TestResultDB(source_id=src.id, tested_at=datetime.utcnow(),
                                                 **{k: result.get(k) for k in fields}))
                        src_db = session.get(SourceDB, src.id)
                        if src_db and result.get('segment_valid') is not None:
                            src_db.status = 'active' if result.get('segment_valid') else 'temporarily_failed'
                        session.flush()
                        if isinstance(result, dict) and result.get('segment_valid') is False:
                            maybe_auto_delete_failed_source(session, src.id)
                        saved += 1
                        is_failed = result.get('segment_valid') is False
                        if is_failed:
                            failed += 1
                        run_db = session.get(SchedulerRunDB, run_id)
                        if run_db:
                            run_db.tested = saved
                            run_db.failed = failed
                            run_db.passed = max(0, saved - failed)
                        session.commit()
            except Exception:
                failed += 1

        final_status = 'completed'
        try:
            await runner.test_many(sources, deep=(mode == 'full'), mode=mode, on_result=save_result)
        except asyncio.CancelledError:
            final_status = 'cancelled'
            raise
        except Exception:
            final_status = 'failed'
            raise
        finally:
            await runner.close()
            finished_at = datetime.utcnow()
            duration = max(0.0, (finished_at - started_at).total_seconds())
            with SessionLocal() as session:
                cfg = self._config(session)
                cfg.last_finished_at = finished_at
                cfg.last_status = final_status
                cfg.last_tested = saved
                cfg.last_failed = failed
                run_db = session.get(SchedulerRunDB, run_id)
                if run_db:
                    run_db.finished_at = finished_at
                    run_db.status = final_status
                    run_db.tested = saved
                    run_db.failed = failed
                    run_db.passed = max(0, saved - failed)
                    run_db.duration_seconds = duration
                session.commit()
        return {'run_id': run_id, 'total': len(sources), 'tested': saved, 'failed': failed, 'mode': mode, 'status': final_status}

    def runs(self, limit: int = 20):
        limit = min(max(1, int(limit)), 100)
        with SessionLocal() as session:
            rows = session.scalars(
                select(SchedulerRunDB).order_by(SchedulerRunDB.started_at.desc()).limit(limit)
            ).all()
            return [{
                'id': r.id, 'started_at': r.started_at, 'finished_at': r.finished_at,
                'status': r.status, 'trigger': r.trigger, 'test_mode': r.test_mode,
                'source_scope': r.source_scope, 'total': r.total, 'tested': r.tested,
                'passed': r.passed, 'failed': r.failed,
                'duration_seconds': r.duration_seconds, 'error_message': r.error_message,
            } for r in rows]

    def status(self):
        with SessionLocal() as session:
            cfg = self._config(session)
            job = self.scheduler.get_job(self.job_id) if self.scheduler.running else None
            full_job = self.scheduler.get_job(self.full_job_id) if self.scheduler.running else None
            return {
                'enabled': cfg.enabled, 'interval_minutes': cfg.interval_minutes,
                'test_mode': cfg.test_mode, 'source_scope': cfg.source_scope,
                'stale_hours': cfg.stale_hours,
                'max_concurrency': cfg.max_concurrency, 'max_host_concurrency': cfg.max_host_concurrency,
                'connect_timeout': cfg.connect_timeout, 'read_timeout': cfg.read_timeout,
                'segment_test_count': cfg.segment_test_count,
                'full_enabled': bool(getattr(cfg, 'full_enabled', False)),
                'full_interval_hours': int(getattr(cfg, 'full_interval_hours', 24) or 24),
                'last_started_at': cfg.last_started_at,
                'last_finished_at': cfg.last_finished_at, 'last_status': cfg.last_status,
                'last_tested': cfg.last_tested, 'last_failed': cfg.last_failed,
                'next_run_at': job.next_run_time if job else None,
                'next_full_run_at': full_job.next_run_time if full_job else None,
                'running': self._run_lock.locked(),
            }

    def update(self, **values):
        with SessionLocal() as session:
            cfg = self._config(session)
            for k, v in values.items():
                if v is not None and hasattr(cfg, k):
                    setattr(cfg, k, v)
            session.commit()
            session.refresh(cfg)
            if cfg.enabled:
                if self.scheduler.running:
                    self._schedule(cfg.interval_minutes)
            elif self.scheduler.running and self.scheduler.get_job(self.job_id):
                self.scheduler.remove_job(self.job_id)
            if self.scheduler.running:
                self._schedule_full(
                    bool(getattr(cfg, 'full_enabled', False)),
                    int(getattr(cfg, 'full_interval_hours', 24) or 24),
                )
        return self.status()


scheduler_service = SchedulerService()
