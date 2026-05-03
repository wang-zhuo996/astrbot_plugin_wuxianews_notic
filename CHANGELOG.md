# Changelog

## [1.0.2] - 2026-05-03

### Changed
- **Markdown 渲染改用 pillowmd**：不再依赖 `astrbot_plugin_nobrowser_markdown_to_pic` 插件的私有方法 `_render_markdown_to_image`，改用 `pillowmd.MdToImage` 直接渲染，移除对外部插件内部实现的耦合。
- **消息发送改用 `send_message_by_id`**：移除手动构造 umo 字符串的 `_unified_msg_origin` 字典，改为直接使用群号通过 `StarTools.send_message_by_id(type="GroupMessage", id=...)` 发送消息，更简洁且兼容不同平台适配器。
- **缓存结构优化**：`_cache_payload` 从 `list[dict]` 改为 `list[NewsJsonIf]`，利用 dataclass 的 `__eq__` 方法直接进行对象比较，移除冗余的 `_cache_keys` 集合和手动 dict 构造。
- **新增图片 URL 转换**：`convert_img_url()` 函数处理公告内容中的相对路径图片，补全为绝对 URL。
- **兼容性调整**：`astrbot_version` 要求从 `>=4.23` 放宽至 `>=4.0`，仅依赖框架基础 API。

### Fixed
- **修复 `set_subscription` 中 `_unified_msg_origin` 残留引用**：订阅管理不再维护已移除的 `_unified_msg_origin` 字典。

## [1.0.1] - 2026-05-03

### Fixed
- **修复 `_ContextLike` 类型错误**：`main.py:85` 中 `self.context.send_message()` 导致类型检查器报错 `属性"send_message"未知`。`Star` 基类将 `self.context` 的类型标注为 `_ContextLike`（仅暴露 `get_config` 的 Protocol），因此无法通过类型检查。改为使用 `StarTools.send_message()` 替代直接调用 `self.context.send_message()`，这是框架推荐的做法（框架启动时已调用 `StarTools.initialize(context)` 完成初始化）。

### Changed
- **新闻对比逻辑改为前10条批量对比**：`compare_json_news_and_update` 重写为 `get_new_news`，每次拉取最新10条新闻与本地存储列表做差集对比，返回所有新出现的新闻（可能多条），逐一推送通知。本地存储格式从单个 JSON 对象改为 JSON 列表（最多10条）。
- **新增内存缓存机制**：插件启动时从文件一次性加载公告缓存到内存（`_cache_keys` / `_cache_payload`），后续所有对比操作在内存中完成，不再每轮频繁读写文件。写回磁盘的时机：
  - 插件卸载时（`terminate` 中调用 `flush_news_cache()`）
  - 连续 N 次（默认10次）无新公告时自动执行检查点写入
- **优化轮询循环逻辑**：当 `enable=False` 时不再空转 `wait_for`，改为每60秒检查一次，减少不必要的循环消耗。启用时保持原有的「先等30秒 → 拉取公告 → 再等 interval-30 秒」节奏不变。
- **整理导入语句**：移除未使用的导入（`MessageEventResult`、`message_components as mc`、`star_handlers_registry`、`star_registry`），并按标准库 → 第三方 → 项目内 分组排列。
- **`msg_chain` 防御性初始化**：在 `match` 分支前显式初始化为 `None`，`match` 无匹配时打印警告并提前 `return`，避免潜在未绑定变量。

### Removed
- 移除 `wuxia_news.py` 中 `NewsContent.__new__` 的死代码：该方法自动创建了一个后台线程和独立事件循环，但从未被实际使用（所有异步任务均在主事件循环上通过 `asyncio.create_task` 执行）。同时移除相关联的 `import threading` 和 `from types import CoroutineType` 导入。
- 移除多余的 `pass` 语句和注释掉的调试日志。
