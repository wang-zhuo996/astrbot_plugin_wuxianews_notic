from typing import Literal
from pydantic import BaseModel
from astrbot.api import AstrBotConfig


# @dataclass
class Notic(BaseModel):
    enable: bool = False
    type: Literal["content", "url"] = "url"
    interval: int = 60


# @dataclass
class Config(AstrBotConfig):
    subscribe: list[str] = []
    notic: Notic = Notic()
    news_cache: bool = False
