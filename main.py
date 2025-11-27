from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult,MessageChain
from astrbot.api.star import Context, Star, register,StarTools
from astrbot.api import logger, message_components as mc
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.star import star_map ,star_registry

import asyncio
from typing import cast

from .wuxia_news import NewsContent, get_notic_news,access_wuxiaofficial_web
from .config import Config




@register("astrbot_plugin_wuxianews_notic", "", "天刀公告获取插件", "1.0.0")
class WuxiaNewsNotic(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._task_event: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._unified_msg_origin = {}
        self.logger = logger

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.logger.info("天刀公告插件初始化")
        self.config = Config(StarTools.get_data_dir("wuxia"))
        await self.config.load_config()
        async def func():
            while True:
                # 业务逻辑
                if self.config.notic.enable:
                    await asyncio.sleep(30)
                    # self.logger.info("开始获取天刀公告")
                    await get_notic_news(self.notic_return_msg)
                # 在循环中，我们可以等待一个很短的时间，同时也可以等待停止事件
                # 这里我们使用asyncio.wait同时等待停止事件和睡眠，以便快速响应停止事件
                done, pending = await asyncio.wait(
                    [self._task_event.wait(), asyncio.sleep(self.config.notic.interval)],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # 如果停止事件被设置，则退出循环
                if self._task_event.is_set():
                    break

        self._task = asyncio.create_task(func())
        pass

    async def notic_return_msg(self, news: NewsContent):
        match self.config.notic.type :
            case "content":
                # 获取插件实例
                mk2img_instanc_metadata = star_map.get("data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main",None)
                if mk2img_instanc_metadata is None:
                    raise ImportError("未加载插件：data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main")
                from data.plugins.astrbot_plugin_nobrowser_markdown_to_pic.main import MyPlugin as Mk2Img
                if isinstance(mk2img_instanc_metadata.star_cls, Mk2Img):
                    mk2img_instanc = cast(Mk2Img, mk2img_instanc_metadata.star_cls)
                    img = await mk2img_instanc._render_markdown_to_image(news.content)
                    img_path = await mk2img_instanc._save_temp_image(img)
                    msg_chain = MessageChain().message(news.url).file_image(img_path)
            case "url":
                msg_chain = MessageChain().message(news.title).message(news.url)
        for qq_group_id in self.config.subscribe:
            if (umo:= self._unified_msg_origin.get(qq_group_id)):
                await self.context.send_message(umo, msg_chain)   
                self.logger.info(f"发送公告到群：{qq_group_id},公告：{news.title} - {news.time}")     

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("公告")
    async def news(self, event: AstrMessageEvent):
        """这是一个 获取公告 指令"""  # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        # user_name = event.get_sender_name()
        # message_str = event.message_str  # 用户发的纯文本消息字符串
        # message_chain = (
        #     event.get_messages()
        # )  # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(event.message_str)
        msg_chain = [
            mc.At(qq=event.get_sender_id()),
            mc.Plain("最近10条公告如下："),
            
        ]
        news_lists  = await access_wuxiaofficial_web()
        for news in news_lists[:10]:
            msg_chain.append(mc.Plain(f"{news.title} - {news.time} - {news.url}"))
               
        yield event.chain_result(msg_chain)

    @filter.command("订阅")
    async def set_subscription(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        if group_id in self._unified_msg_origin:
            self._unified_msg_origin.pop(group_id)
            self.logger.info(f"取消订阅uid：{group_id},{umo}")
            yield event.plain_result("取消订阅成功！")
        else:
            self._unified_msg_origin.update({group_id: umo})
            self.logger.info(f"添加订阅uid：{group_id},{umo}")
            yield event.plain_result("订阅成功！")
        

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        self._task_event.set()
        if self._task:
            await self._task
