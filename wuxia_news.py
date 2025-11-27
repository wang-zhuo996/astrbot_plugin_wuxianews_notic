import asyncio
import json
import os
import re
import threading

import aiofiles
import aiofiles.os
import aiohttp

from bs4 import BeautifulSoup
from bs4.element import Tag
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from types import CoroutineType
from typing import Callable,cast

from astrbot import logger
from astrbot.api.star import StarTools

try:
    from html_to_markdown import convert
except ImportError:
    logger.error("html_to_markdown 未安装，请使用 pip install html_to_markdown 安装")

WUXIA_OFFICAL_URL = "https://wuxia.qq.com"
WUXIA_OFFICAL_NEWSLISTS_PREFIXX = (
    "https://wuxia.qq.com/webplat/info/news_version3/5012/5013/5014/m3485/list_"
)
WUXIA_OFFICAL_NEWSLISTS_URL = (
    "https://wuxia.qq.com/webplat/info/news_version3/5012/5013/5014/m3485/list_{}.shtml"
)
HEAD = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
}


class NewsContent:
    __event_loop: asyncio.AbstractEventLoop
    # _tasks: list[asyncio.Task] = []

    def __new__(cls, *arg, **kwargs):
        # cls = super().__new__(cls)
        setattr(cls, f"_{cls.__name__}__event_loop", asyncio.get_event_loop())
        if not cls.__event_loop.is_running():
            cls.__thread = threading.Thread(
                target=cls.__event_loop.run_forever,
                name="NewsContentAsyncLoop",
                daemon=False,
            )
            cls.__thread.start()

        return super().__new__(cls)

    def __init__(
        self,
        url: str,
        title: str = "",
        tag: str = "",
        time: str = "",
        content="",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.tag = tag
        self.time = time
        self.content = content
        self.logger = logger
        if session:
            self.add_task(self.get_content(session))
        pass

    def add_task(self, coroutine):
        self.wait_task = asyncio.create_task(coroutine)
        # self.__class__._tasks.append(self.wait_task)

    async def get_content(self, session: aiohttp.ClientSession):
        # await asyncio.sleep(10)
        # print("get_content") Task exception was never retrieved
        async with session.get(self.url, headers=HEAD) as resp:
            soup = BeautifulSoup(await resp.read(), "lxml")
            news_content = soup.find("div", attrs={"class": "newsconcent details"})
            if news_content:
                title = news_content.find("div", attrs={"class": "ahd"})
                content = news_content.find("div", attrs={"class": "artws"})
            if title and content:
                self.content = title.prettify() + "\n" + content.prettify()
            self.content = convert_star(self.content)
            self.content = merge_bold(convert(self.content))
            self.logger.info(f"{self.title} 获取公告内容完成")
            # with open(f"{self.title}.md", "w", encoding="utf-8") as f:
            #     f.write(self.content)

    async def save(self, path: str = ""):
        if not path:
            raise ValueError("未指定保存路径")
        else:
            data_path = Path(path)

        if not await aiofiles.os.path.exists(data_path):
            await aiofiles.os.makedirs(os.path.join(data_path, self.tag))

        file_name = os.path.join(
            data_path,
            self.tag,
            self.time + "_" + re.sub(r'[\\/:*?"<>|]', "_", self.title) + ".md",
        )
        async with aiofiles.open(file_name, mode="w", encoding="utf-8") as f:
            await f.write(self.content)


class NewsListIndex:
    _total_index: int

    def __init__(self, index: str | int):
        self.index: int
        self.truth_index: int
        self.is_historical = False
        if isinstance(index, int):
            self.index = index
            self.truth_index = self.index
        else:
            if index.startswith("n"):
                self.index = int(index.removeprefix("n"))
                self.is_historical = True
                self.truth_index = NewsListIndex._total_index - self.index + 1
            else:
                self.index = int(index)
                self.truth_index = self.index
        if self.truth_index > 3 and not self.is_historical:
            self.is_historical = True
            self.index = self._total_index - self.truth_index + 1
        if self.truth_index < 1:
            raise IndexError("超过最小索引")
        if hasattr(self, "_total_index"):
            if self.truth_index > self._total_index:
                raise IndexError("超过最大索引")

    def __repr__(self):
        if self.is_historical:
            return f"n{self.index}"
        else:
            return f"{self.index}"
        pass

    def __str__(self):
        if self.is_historical:
            return f"n{self.index}"
        else:
            return f"{self.index}"
        pass

    def next(self):
        if self.truth_index + 1 > self._total_index:
            raise IndexError("超过最大索引")
        return NewsListIndex(self.truth_index + 1)

    def previous(self):
        if self.truth_index - 1 < 1:
            raise IndexError("超过最小索引")
        return NewsListIndex(self.truth_index - 1)


bold_compare_rule = re.compile(r"(\*\*[^\*]+\*?[^\*]{0,}\*\*( )?){2,}")
star_compare_rule = re.compile(r"([^*]\*[^*])")


async def wuxia_get_newslists_index() -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            WUXIA_OFFICAL_NEWSLISTS_URL.format(3), headers=HEAD
        ) as res:
            soup = BeautifulSoup(await res.read(), "lxml")
    historical_accumulation_index = soup.find("div", attrs={"class": "cpages"})
    if historical_accumulation_index:
        for child in historical_accumulation_index.children:
            if child.text == "下一页 >":
                next_page_element = cast(Tag,child)
                break
    historical_index = (
        cast(str,next_page_element.attrs.get("href"))
        .removeprefix(WUXIA_OFFICAL_NEWSLISTS_PREFIXX.removeprefix(WUXIA_OFFICAL_URL))
        .removesuffix(".shtml")
    )
    NewsListIndex._total_index = int(historical_index.removeprefix("n")) + 3
    return NewsListIndex._total_index


async def access_wuxiaofficial_web(
    page: NewsListIndex = NewsListIndex(1), list_index: int | None = None
) -> list[NewsContent]:

    async with aiohttp.ClientSession() as session:
        async with session.get(
            WUXIA_OFFICAL_NEWSLISTS_URL.format(page), headers=HEAD
        ) as resp:
            # res = requests.get(WUXIA_OFFICAL_NEWSLISTS_URL.format(page), headers=HEAD)
            soup = BeautifulSoup(await resp.read(), "lxml")
    newlist = t.find_all("li") if (t:= soup.find("ul", attrs={"class": "newslists"})) else None
    if newlist is None:
        raise ValueError("未找到新闻列表")
    newlist_objs: list[NewsContent] = []
    session = aiohttp.ClientSession()
    cnts = 0
    for item in newlist:
        title_ele = item.find("a", {"class": "cltit"})
        tag_ele = item.find("a", {"class": "cltag"})
        time_ele = item.find("span", {"class": "cltime"})
        if time_ele and title_ele and tag_ele:
            new_obj = NewsContent(
                url=WUXIA_OFFICAL_URL + str(title_ele.attrs.get("href")),
                title=title_ele.text,
                tag=tag_ele.text,
                time=time_ele.text,
                session=session,
            )
        if list_index is None:
            newlist_objs.append(new_obj)
            logger.info(f"{new_obj.title} 已添加")
        else:
            if list_index == cnts:
                newlist_objs.append(new_obj)
                logger.info(f"{new_obj.title} 已添加")
                break
        cnts += 1

    await asyncio.gather(*list(map(lambda x: x.wait_task, newlist_objs)))
    await session.close()
    return newlist_objs


def merge_bold(linetext: str):
    match_bold = re.finditer(bold_compare_rule, linetext)
    if match_bold:
        for item in match_bold:
            linetext = linetext.replace(
                item.group(), "**" + item.group().replace("**", "") + "**", 1
            )

    return linetext


def convert_star(linetext: str):
    match_star = re.finditer(star_compare_rule, linetext)
    if match_star:
        for item in match_star:
            linetext = linetext.replace(item.group(), item.group().replace("*", r"\*"))
    return linetext


@dataclass
class NewsJsonIf:
    tag: str
    title: str
    time: str
    content_md5: str

    def __eq__(self, other):
        if type(other) == NewsJsonIf:
            return (
                self.tag == other.tag
                and self.title == other.title
                and self.time == other.time
                and self.content_md5 == other.content_md5
            )
        else:
            return False


async def compare_json_news_and_update(obj: NewsContent):
    lasts_info_file = os.path.join(StarTools.get_data_dir("wuxia"), "wuxia_news_lastsif.json")
    if await aiofiles.os.path.exists(lasts_info_file):
        
        async with aiofiles.open(lasts_info_file, "r", encoding="utf-8") as f:
            jsonif = NewsJsonIf(**json.loads(await f.read()))
    
        if obj.tag == jsonif.tag and obj.title == jsonif.title and obj.time == jsonif.time:
            obj_md5 = md5(obj.content.encode("utf-8"))
            if obj_md5.hexdigest() == jsonif.content_md5:
                return True
            
    async with aiofiles.open(lasts_info_file, "w", encoding="utf-8") as f:
        will_write_news = NewsJsonIf(
            tag=obj.tag,
            title=obj.title,
            time=obj.time,
            content_md5=md5(obj.content.encode("utf-8")).hexdigest(),
        )
        await f.write(json.dumps(will_write_news.__dict__, ensure_ascii=False))
    return False


async def load_lasts_news_jsonif():
    lasts_info_file = os.path.join(StarTools.get_data_dir("wuxia"), "wuxia_news_lastsif.json")
    async with aiofiles.open(lasts_info_file, "r", encoding="utf-8") as f:
        jsonif = NewsJsonIf(**json.loads(await f.read()))
    return jsonif


async def get_notic_news(callback: Callable[[NewsContent], CoroutineType]):
    logger.info("开始获取最新公告 ...")
    lasts_news = await access_wuxiaofficial_web(list_index=0)
    lasts_new = lasts_news[0]
    if await compare_json_news_and_update(lasts_new):
        logger.info("没有发现最新公告")
        return None
    else:
        logger.info(f"发现最新公告: {lasts_new.title}")
        return await callback(lasts_new)


async def main():
    await wuxia_get_newslists_index()
    news_lists = await access_wuxiaofficial_web()
    for news in news_lists:
        await news.save()
    # for _ in range(620):
    #     try:
    #         print(NewsListIndex(_))
    #     except IndexError:
    #         print(f"{_}超过索引")


if __name__ == "__main__":
    asyncio.run(main())
