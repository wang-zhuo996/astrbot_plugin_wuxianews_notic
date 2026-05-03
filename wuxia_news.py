import asyncio
import json
import os
import re

import aiofiles
import aiofiles.os
import aiohttp

from bs4 import BeautifulSoup
from bs4.element import Tag
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from typing import Awaitable, Callable, Protocol, cast

from astrbot import logger
from astrbot.api.star import StarTools

try:
    from html_to_markdown import convert,ConversionResult
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
            self.content = convert_img_url(convert(self.content))
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

    def __str__(self):
        if self.is_historical:
            return f"n{self.index}"
        else:
            return f"{self.index}"

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
    page: NewsListIndex = NewsListIndex(1), list_index: int | None = None,content_type: str = 'url'
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
    logger.debug(newlist)
    newlist_objs: list[NewsContent] = []
    if content_type == 'url':
        session = None
    elif content_type == 'content':
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
            logger.debug(new_obj.__dict__)
        else:
            if list_index == cnts:
                newlist_objs.append(new_obj)
                logger.info(f"{new_obj.title} 已添加")
                break
        cnts += 1

    if session:
        await asyncio.gather(*list(map(lambda x: x.wait_task, newlist_objs)))
        logger.debug("等待完成")
        await session.close()
    return newlist_objs

def convert_img_url(res:ConversionResult) -> str:
    if res.content:
        return res.content.replace("![](//", "![](https://")
    return ''

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


# ---------------------------------------------------------------------------
# 内存缓存：避免频繁读写磁盘，仅在初始化/卸载/定期检查点写文件
# ---------------------------------------------------------------------------
_FLUSH_ON_NO_DIFF_COUNT: int = 10
_cache_keys: set[str] | None = None
_cache_payload: list[dict] | None = None
_cache_no_diff_count: int = 0


class _HasTagTitleTime(Protocol):
    tag: str
    title: str
    time: str


def _make_json_key(news: _HasTagTitleTime) -> str:
    """用 (tag, title, time) 生成新闻的唯一标识键。"""
    return f"{news.tag}\x00{news.title}\x00{news.time}"


async def init_news_cache():
    """插件启动时调用：读取本地 JSON 文件并加载到内存缓存。"""
    global _cache_keys, _cache_payload, _cache_no_diff_count

    lasts_info_file = os.path.join(
        StarTools.get_data_dir("wuxia"), "wuxia_news_lastsif.json"
    )
    _cache_keys = set()
    _cache_payload = []
    _cache_no_diff_count = 0

    if await aiofiles.os.path.exists(lasts_info_file):
        async with aiofiles.open(lasts_info_file, "r", encoding="utf-8") as f:
            try:
                stored_list: list[dict] = json.loads(await f.read())
                _cache_keys = {
                    _make_json_key(NewsJsonIf(**item)) for item in stored_list
                }
                _cache_payload = stored_list
                logger.info(f"公告缓存已加载，共 {len(_cache_keys)} 条记录")
            except (json.JSONDecodeError, KeyError):
                logger.warning("本地公告缓存解析失败，将视为全新获取")
    else:
        logger.info("公告缓存文件不存在，初始化为空")


async def flush_news_cache():
    """将内存缓存写回本地 JSON 文件（在插件卸载或定期检查点时调用）。"""
    global _cache_no_diff_count

    lasts_info_file = os.path.join(
        StarTools.get_data_dir("wuxia"), "wuxia_news_lastsif.json"
    )
    if _cache_payload is not None:
        async with aiofiles.open(lasts_info_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(_cache_payload, ensure_ascii=False))
        logger.info("公告缓存已写入文件")
    _cache_no_diff_count = 0


async def get_new_news(news_list: list[NewsContent]) -> list[NewsContent]:
    """对比前 n 条新闻与内存缓存，返回不在缓存中的新新闻。

    所有对比操作在内存中完成；仅在无差异累积到阈值或外部显式调用
    flush_news_cache() 时才写入文件。
    """
    global _cache_keys, _cache_payload, _cache_no_diff_count

    if _cache_keys is None:
        raise RuntimeError("公告缓存尚未初始化，请先调用 init_news_cache()")

    # 筛选新新闻
    new_items: list[NewsContent] = []
    for news in news_list:
        if _make_json_key(news) not in _cache_keys:
            new_items.append(news)

    # 用最新拉取的前10条更新缓存
    top10 = news_list[:10]
    _cache_keys = {_make_json_key(n) for n in top10}
    _cache_payload = [
        {
            "tag": n.tag,
            "title": n.title,
            "time": n.time,
            "content_md5": md5(n.content.encode()).hexdigest() if n.content else "",
        }
        for n in top10
    ]

    if new_items:
        _cache_no_diff_count = 0
    else:
        _cache_no_diff_count += 1
        if _cache_no_diff_count >= _FLUSH_ON_NO_DIFF_COUNT:
            await flush_news_cache()
            logger.info(
                f"连续 {_FLUSH_ON_NO_DIFF_COUNT} 次无新公告，已自动写入缓存"
            )

    return new_items


async def load_lasts_news_jsonif() -> list[NewsJsonIf]:
    """加载本地存储的公告缓存列表（直接读文件，不走内存缓存）。"""
    lasts_info_file = os.path.join(
        StarTools.get_data_dir("wuxia"), "wuxia_news_lastsif.json"
    )
    if await aiofiles.os.path.exists(lasts_info_file):
        async with aiofiles.open(lasts_info_file, "r", encoding="utf-8") as f:
            return [NewsJsonIf(**item) for item in json.loads(await f.read())]
    return []


async def get_notic_news(callback: Callable[[NewsContent], Awaitable[None]]):
    """获取最新公告列表，对比本地缓存后，对每条新公告调用回调通知。"""
    logger.info("开始获取最新公告 ...")
    lasts_news = await access_wuxiaofficial_web()
    top10 = lasts_news[:10]
    new_news = await get_new_news(top10)

    if not new_news:
        logger.info("没有发现最新公告")
        return

    logger.info(f"发现 {len(new_news)} 条最新公告")
    for news in new_news:
        logger.info(f"  - {news.title} ({news.time})")
        await callback(news)


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
