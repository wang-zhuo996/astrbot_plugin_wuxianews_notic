import asyncio
from typing import cast

from aiohttp import ClientSession

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.star.star import star_map
from astrbot.core.platform.message_session import MessageSesion
import pillowmd

from .config import Config, Notic
from .wuxia_news import (
    NewsContent,
    access_wuxiaofficial_web,
    flush_news_cache,
    get_notic_news,
    init_news_cache,
)


@register("astrbot_plugin_wuxianews_notic", "", "天刀公告获取插件", "1.0.0")
class WuxiaNewsNotic(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self._task_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.logger = logger
        self.config = cast(Config, config)
        self.conf_notic = Notic.model_validate(self.config.notic)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.logger.info("天刀公告插件初始化")
        await init_news_cache()

        async def func():
            while True:
                if not self.conf_notic.enable:
                    # 未启用通知时，等待事件即可
                    try:
                        await asyncio.wait_for(
                            self._task_event.wait(),
                            timeout=60,
                        )
                        break
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

                await asyncio.sleep(30)
                await get_notic_news(self.notic_return_msg)

                try:
                    await asyncio.wait_for(
                        self._task_event.wait(),
                        timeout=self.conf_notic.interval - 30,
                    )
                    break
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        self._task = asyncio.create_task(func())
        self.logger.info("天刀公告插件初始化完成")

    async def notic_return_msg(self, news: NewsContent):
        msg_chain: MessageChain | None = None
        match self.conf_notic.type:
            case "content":
                mk2img_instanc_metadata = star_map.get(
                    "data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main", None
                )
                if mk2img_instanc_metadata is None:
                    raise ImportError(
                        "未加载插件：data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main"
                    )
                from data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main import (
                    MyPlugin as Mk2Img,
                )

                if isinstance(mk2img_instanc_metadata.star_cls, Mk2Img):
                    mk2img_instanc = cast(Mk2Img, mk2img_instanc_metadata.star_cls)
                    img = await pillowmd.MdToImage(news.content, useImageUrl=True)
                    img_path = await mk2img_instanc._save_temp_image(img)
                    msg_chain = MessageChain().message(news.url).file_image(img_path)

            case "url":
                msg_chain = MessageChain().message(news.title).message(news.url)

        if msg_chain is None:
            self.logger.warning(f"未知的通知类型: {self.conf_notic.type}")
            return

        for qq_group_id in self.config.subscribe:
            await StarTools.send_message_by_id(
                type="GroupMessage", id=qq_group_id, message_chain=msg_chain
            )
            self.logger.info(
                f"发送公告到群：{qq_group_id}, 公告：{news.title} - {news.time}"
            )

    @filter.command("公告")
    async def news(self, event: AstrMessageEvent):
        """这是一个 获取公告 指令"""
        logger.info(event.message_str)
        msg_chain = ["\n最近10条公告如下：\n"]
        news_lists = await access_wuxiaofficial_web()
        for news in news_lists[:10]:
            msg_chain.append(f"{news.title} - {news.time} - {news.url}\n")
        yield event.plain_result("".join(msg_chain))

    @filter.command("订阅")
    async def set_subscription(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        if group_id in self.config.subscribe:
            self.config.subscribe.remove(group_id)
            self.logger.info(f"取消订阅uid：{group_id},{umo}")
            yield event.plain_result("取消订阅成功！")
        else:
            self.config.subscribe.append(group_id)
            self.logger.info(f"添加订阅uid：{group_id},{umo}")
            yield event.plain_result("订阅成功！")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        self._task_event.set()
        await flush_news_cache()
        self.config.save_config()
