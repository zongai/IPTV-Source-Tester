import asyncio
import json
from datetime import datetime
from pathlib import Path

import typer
from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.init_db import init_db
from app.database.locks import db_write_lock
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.database.repository import maybe_auto_delete_failed_source, retain_ffprobe_media_fields
from app.exporters.m3u import render_m3u
from app.parser.m3u import parse_m3u
from app.parser.normalizer import infer_default_group
from app.services.import_service import import_entries
from app.services.test_service import TestRunner

app = typer.Typer(help='IPTV Source Tester V4')


@app.command('import')
def import_playlist(path: str):
    init_db()
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    entries = parse_m3u(text)
    with SessionLocal() as session:
        result = import_entries(session, entries, Path(path).name)
    typer.echo(json.dumps({'parsed': len(entries), **result}, ensure_ascii=False))


@app.command()
def test(deep: bool = False, duration: int = 0, channel: str = ''):
    """Test enabled sources. duration is reserved for future continuous stability mode."""
    init_db()
    with SessionLocal() as session:
        stmt = select(SourceDB).where(SourceDB.enabled.is_(True))
        if channel:
            stmt = stmt.where(SourceDB.channel_id == channel)
        sources = list(session.scalars(stmt))
    async def run():
        runner = TestRunner()
        fields = ('dns_latency','ttfb','http_status','content_type','playlist_valid','segment_valid',
                  'video_codec','audio_codec','width','height','fps','bitrate','download_speed',
                  'min_speed','max_speed','startup_time','stability','failure_rate','score',
                  'error_type','error_message','ffprobe_json')
        async def save(_, src, result):
            if isinstance(result, Exception):
                result = {'segment_valid': False, 'playlist_valid': False,
                          'error_type': 'INTERNAL_ERROR', 'error_message': str(result)[:1000]}
            async with db_write_lock:
                with SessionLocal() as session:
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
                    session.commit()
        try:
            results = await runner.test_many(sources, deep=deep, mode='full' if deep else 'standard', on_result=save)
            ok = sum(1 for r in results if isinstance(r, dict) and r.get('segment_valid') is True)
            return len(results), ok
        finally:
            await runner.close()
    total, ok = asyncio.run(run())
    if duration:
        typer.echo('Note: --duration is not yet a continuous stability run; the normal test completed.')
    typer.echo(f'tested={total} passed={ok} failed={total-ok}')


@app.command()
def export(format: str = 'm3u', output: str = ''):
    """Export the latest validated passing sources."""
    from app.api.playlists import payload
    data = payload()
    if format.lower() == 'json':
        content = json.dumps(data, ensure_ascii=False, indent=2)
    elif format.lower() == 'm3u':
        entries = []
        for c in data['channels']:
            for source in c['sources']:
                headers = {k: source[k] for k in ('user_agent','referer','origin','cookie','authorization') if source.get(k)}
                group_title = (
                    source.get('group')
                    or c.get('group')
                    or infer_default_group(c.get('name'), c.get('id'))
                    or ''
                )
                entries.append({'name': c['name'], 'url': source['url'], 'attrs': {
                    'tvg-id': c['id'], 'tvg-name': c['name'], 'tvg-logo': c['logo'],
                    'group-title': group_title,
                }, 'headers': headers})
        content = render_m3u(entries)
    else:
        raise typer.BadParameter('format must be m3u or json')
    if output:
        Path(output).write_text(content, encoding='utf-8')
        typer.echo(output)
    else:
        typer.echo(content, nl=False)


@app.command()
def stats():
    init_db()
    with SessionLocal() as s:
        channels = s.query(ChannelDB).count()
        sources = s.query(SourceDB).count()
        passed = s.query(TestResultDB).filter(TestResultDB.segment_valid.is_(True)).count()
    typer.echo(json.dumps({'channels': channels, 'sources': sources, 'passing_test_results': passed}, ensure_ascii=False))


@app.command()
def channels():
    init_db()
    with SessionLocal() as s:
        for x in s.scalars(select(ChannelDB)).all():
            typer.echo(f'{x.id}\t{x.display_name}')


@app.command()
def sources():
    init_db()
    with SessionLocal() as s:
        for x in s.scalars(select(SourceDB)).all():
            typer.echo(f'{x.id}\t{x.channel_id}\t{x.status}\t{x.url}')


if __name__ == '__main__':
    app()
