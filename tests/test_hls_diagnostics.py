import asyncio
from aiohttp import web, ClientSession
from app.tester.hls import check_hls


def test_hls_segment_error_preserves_reason():
    async def scenario():
        async def playlist(_):
            return web.Response(text='#EXTM3U\n#EXTINF:4,\na.ts\n#EXTINF:4,\nb.ts\n')
        async def segment(_):
            return web.Response(status=404, text='no')
        app = web.Application()
        app.router.add_get('/live.m3u8', playlist)
        app.router.add_get('/{name}.ts', segment)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        async with ClientSession() as session:
            result = await check_hls(f'http://127.0.0.1:{port}/live.m3u8', session, 2)
        await runner.cleanup()
        return result

    result = asyncio.run(scenario())
    assert result.valid is False
    assert result.error_type == 'HTTP_404'
    assert result.segment_details[0]['status'] == 404
