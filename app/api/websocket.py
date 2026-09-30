from fastapi import APIRouter,WebSocket,WebSocketDisconnect
router=APIRouter();clients=set()
@router.websocket('/ws/tests')
async def tests(ws:WebSocket):
 await ws.accept();clients.add(ws)
 try:
  while True:await ws.receive_text()
 except WebSocketDisconnect:clients.discard(ws)
async def broadcast(data):
 for ws in list(clients):
  try:await ws.send_json(data)
  except Exception:clients.discard(ws)
