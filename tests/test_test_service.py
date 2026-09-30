import asyncio
from types import SimpleNamespace
from aiohttp import web
from app.services.test_service import TestRunner as IPTVTestRunner


def test_standard_result_contains_http_and_speed_metrics():
    async def scenario():
        async def playlist(_):
            return web.Response(text='#EXTM3U\n#EXTINF:1,\na.ts\n#EXTINF:1,\nb.ts\n#EXTINF:1,\nc.ts\n#EXT-X-ENDLIST\n')
        async def segment(_):
            return web.Response(body=b'x' * 4096, content_type='video/mp2t')
        app = web.Application()
        app.router.add_get('/live.m3u8', playlist)
        app.router.add_get('/{name}.ts', segment)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        source = SimpleNamespace(
            url=f'http://127.0.0.1:{port}/live.m3u8', host='127.0.0.1',
            user_agent=None, referer=None, origin=None, cookie=None, authorization=None,
        )
        tester = IPTVTestRunner(max_concurrency=2, max_host_concurrency=2, segment_test_count=3)
        try:
            result = await tester.test_source(source, deep=False, mode='standard')
            return result
        finally:
            await tester.close()
            await runner.cleanup()

    result = asyncio.run(scenario())
    assert result['http_status'] == 200
    assert result['playlist_valid'] is True
    assert result['segment_valid'] is True
    assert result['download_speed'] is not None
    assert result['min_speed'] is not None
    assert result['max_speed'] is not None
    assert result['score'] is not None


def test_standard_connection_failure_is_failed_and_full_is_failed():
    async def scenario():
        import app.services.test_service as mod
        source = SimpleNamespace(
            url='http://dead.example/live.m3u8', host='dead.example',
            user_agent=None, referer=None, origin=None, cookie=None, authorization=None,
        )
        original = mod.check_connectivity
        async def fake(*args, **kwargs):
            return SimpleNamespace(ok=False, status=None, error_type='TIMEOUT', error_message='connect timed out',
                                   dns_latency=None, ttfb=None, content_type=None)
        mod.check_connectivity = fake
        tester = IPTVTestRunner(max_concurrency=2, max_host_concurrency=1)
        try:
            standard = await tester.test_source(source, mode='standard')
            full = await tester.test_source(source, mode='full')
            quick = await tester.test_source(source, mode='quick')
            return standard, full, quick
        finally:
            mod.check_connectivity = original
            await tester.close()

    standard, full, quick = asyncio.run(scenario())
    for result in (standard, full):
        assert result['segment_valid'] is False
        assert result['playlist_valid'] is False
        assert result['error_type'] == 'TIMEOUT'
        assert result['error_message'] == 'connect timed out'
    assert quick['segment_valid'] is None


def test_success_result_has_no_error_message():
    async def scenario():
        async def playlist(_):
            return web.Response(text='#EXTM3U\n#EXTINF:1,\na.ts\n#EXTINF:1,\nb.ts\n#EXTINF:1,\nc.ts\n#EXT-X-ENDLIST\n')
        async def segment(_):
            return web.Response(body=b'x' * 4096, content_type='video/mp2t')
        app = web.Application()
        app.router.add_get('/live.m3u8', playlist)
        app.router.add_get('/{name}.ts', segment)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        source = SimpleNamespace(url=f'http://127.0.0.1:{port}/live.m3u8', host='127.0.0.1',
                                 user_agent=None, referer=None, origin=None, cookie=None, authorization=None)
        tester = IPTVTestRunner(max_concurrency=2, max_host_concurrency=2, segment_test_count=3)
        try:
            return await tester.test_source(source, mode='standard')
        finally:
            await tester.close()
            await runner.cleanup()
    result = asyncio.run(scenario())
    assert result['segment_valid'] is True
    assert result.get('error_type') is None
    assert result.get('error_message') is None


def test_sources_are_interleaved_by_host():
    sources = [SimpleNamespace(host='a') for _ in range(4)] + [SimpleNamespace(host='b') for _ in range(3)] + [SimpleNamespace(host='c')]
    ordered = IPTVTestRunner._interleave_by_host(list(enumerate(sources)))
    hosts = [src.host for _, src in ordered]
    assert hosts == ['a', 'b', 'c', 'a', 'b', 'a', 'b', 'a']
