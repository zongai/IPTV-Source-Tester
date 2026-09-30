from fastapi import APIRouter, Depends, Query
from app.api.auth import require_admin
from app.tester.network import check_network

router = APIRouter()


@router.get('/network/check', dependencies=[Depends(require_admin)])
async def network_check(target: str = Query('https://example.com', min_length=3, max_length=2048)):
    return (await check_network(target)).to_dict()
