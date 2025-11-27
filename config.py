import json
import aiofiles
from aiofiles.os import path as aio_path
import asyncio
from pathlib import Path
import os
from dataclasses import dataclass
from typing import Literal
@dataclass
class Notic:
    enable: bool = False 
    type: Literal["content",'url'] = "url"
    interval: int = 60

class Config:
    def __init__(self, config_path: Path):
        self.config_path = os.path.join(config_path , "config.json")
        self.subscribe: list[str]  = []
        self.notic: Notic = Notic()
        self.news_cache: bool  = False

    async def load_config(self):
        if await aio_path.exists(self.config_path):
            async with aiofiles.open(self.config_path, "r", encoding="utf-8") as f:
                config: dict = json.loads(await f.read())
        else:
            config = {}
            await self.save_config()
        self.subscribe = config.get("subscribe", [])
        self.notic = Notic(**config.get(
            "notic", {"enable": False, "type": "url", "interval": 60}
        ))
        self.news_cache = config.get("news_cache", False)

    async def save_config(self):
        async with aiofiles.open(self.config_path, "w", encoding="utf-8") as f:
            dumps = json.dumps(
                {
                    "subscribe": self.subscribe,
                    "notic": self.notic.__dict__,
                    "news_cache": self.news_cache,
                },
                ensure_ascii=False,
                indent=4,
            )
            await f.write(dumps)



