import asyncio

# SQLite has a single writer. Keep all in-process write commits behind one
# lock so manual tests, scheduled tests and playlist imports cannot fight.
db_write_lock = asyncio.Lock()
