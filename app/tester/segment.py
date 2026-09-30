from app.tester.hls import check_hls
async def check_segments(url,session,count=3,headers=None):return await check_hls(url,session,segment_count=count,headers=headers)
