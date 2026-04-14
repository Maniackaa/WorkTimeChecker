import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Заполняется в main_max.py перед polling
http_session: aiohttp.ClientSession | None = None
scheduler: AsyncIOScheduler | None = None
