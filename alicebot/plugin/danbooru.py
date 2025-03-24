import random
import bs4
import base64
import aiohttp
import re
from typing import Optional
from typing import Callable, Any
import traceback

log_func: Callable[[Any], None]
plugin_context: Any  # 插件上下文，由插件管理器传入

from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(
    plugin_context.onebot_package_path, log_func=log_func
)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(
    plugin_context.message_codec_package_path, log_func=log_func
)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)


entity_name = "Danbooru"

danbooru_help = r"""
Danbooru Plugin Help
- #danbooru: 获取一个随机 Danbooru 帖子
- #danbooru tag1 tag2: 获取包含指定标签的随机帖子
- #danbooru-page 5: 获取第5页的随机帖子
- #danbooru-page 3 tag1 tag2: 获取第3页中包含特定标签的随机帖子
"""


class Danbooru:
    async def get_random_post(
        tags: Optional[str] = None, page: Optional[int] = None
    ) -> Optional[dict]:
        """获取一个随机 Danbooru 帖子，返回标签和图片 URL

        参数:
            tags: 可选，指定标签查询，多个标签用空格分隔
            page: 可选，指定页码，默认为随机页码
        """
        # 构建URL，如果有标签就添加到查询中
        base_url = "https://danbooru.donmai.us/posts"

        # 页码处理
        if page is None:
            random_page = random.randint(1, 100)
            page_param = f"page={random_page}"
            log_func("INFO", entity_name, f"随机页面: {random_page}")
        else:
            page_param = f"page={page}"
            log_func("INFO", entity_name, f"指定页面: {page}")

        # URL构建
        if tags:
            # 替换空格为加号(+)，适合URL查询
            formatted_tags = tags.replace(" ", "+")
            url = f"{base_url}?tags={formatted_tags}&{page_param}"
            log_func("INFO", entity_name, f"按标签搜索: {tags}")
        else:
            url = f"{base_url}?{page_param}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    log_func(
                        "ERROR", entity_name, f"获取帖子列表失败: {response.status}"
                    )
                    return None

                html = await response.text()

                # 使用 Beautiful Soup 解析 HTML
                soup = bs4.BeautifulSoup(html, "html.parser")

                # 找到所有的帖子元素
                posts = soup.select("article.post-preview")
                if not posts:
                    log_func("ERROR", entity_name, "没有找到帖子元素")
                    return None

                # 随机选择一个帖子
                post = random.choice(posts)

                # 获取帖子ID
                post_id = post.get("data-id", "")
                if not post_id:
                    log_func("ERROR", entity_name, "无法获取帖子ID")
                    return None

                # 获取标签
                post_tags = post.get("data-tags", "")
                if post_tags:
                    # 处理标签格式
                    post_tags = bs4.BeautifulSoup(post_tags, "html.parser").get_text()
                    post_tags = post_tags.replace(" ", ", ")
                    post_tags = post_tags.replace("(", "\\(").replace(")", "\\)")
                    post_tags = post_tags.replace("[", "\\[").replace("]", "\\]")
                    post_tags = post_tags.replace("{", "\\{").replace("}", "\\}")

                # 构造帖子详情页URL
                post_link = f"https://danbooru.donmai.us/posts/{post_id}"

                # 访问帖子详情页获取原图
                log_func("INFO", entity_name, f"访问帖子详情页: {post_link}")
                async with session.get(post_link) as detail_response:
                    if detail_response.status != 200:
                        log_func(
                            "ERROR",
                            entity_name,
                            f"获取帖子详情失败: {detail_response.status}",
                        )
                        return None

                    detail_html = await detail_response.text()
                    detail_soup = bs4.BeautifulSoup(detail_html, "html.parser")

                    # 尝试找到原图元素
                    img_element = detail_soup.select_one(
                        "section.image-container picture img"
                    )
                    if not img_element:
                        # 尝试备用选择器
                        img_element = detail_soup.select_one(
                            "section.image-container img"
                        )

                    img_url = ""
                    if img_element:
                        img_url = img_element.get("src", "")
                        if not img_url:
                            # 尝试其他属性
                            img_url = img_element.get(
                                "data-large-file-url"
                            ) or img_element.get("data-file-url")

                    # 如果还是找不到，尝试从原页面获取
                    if not img_url:
                        log_func(
                            "INFO",
                            entity_name,
                            "无法从详情页获取图片，尝试从列表页获取",
                        )
                        source_element = post.select_one("source")
                        if source_element:
                            srcset = source_element.get("srcset", "")
                            if srcset:
                                parts = srcset.split(",")
                                if parts:
                                    last_part = parts[-1].strip()
                                    img_url = last_part.split(" ")[0]

                        if not img_url:
                            img_element = post.select_one("img")
                            if img_element:
                                img_url = (
                                    img_element.get("data-large-file-url")
                                    or img_element.get("data-file-url")
                                    or img_element.get("src", "")
                                )

                # 添加调试信息
                log_func("INFO", entity_name, f"Found post with ID: {post_id}")
                log_func("INFO", entity_name, f"Image URL: {img_url}")

                return {
                    "tags": post_tags,
                    "img_url": img_url,
                    "post_id": post_id,
                    "post_link": post_link,
                }

    async def get_random_post_and_encode(
        tags: Optional[str] = None, page: Optional[int] = None
    ) -> Optional[str]:
        """获取一个随机 Danbooru 帖子，并返回编码后的消息

        参数:
            tags: 可选，指定标签查询，多个标签用空格分隔
            page: 可选，指定页码，默认为随机
        """
        post = await Danbooru.get_random_post(tags, page)
        if not post:
            return None

        tags = post["tags"]
        img_url = post["img_url"]
        post_link = post["post_link"]

        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as response:
                if response.status != 200:
                    return None
                img_data = await response.read()
                # 将图片数据编码为 base64
                img_base64 = base64.b64encode(img_data).decode("utf-8")
                # 构造图片 URL
                img_url = f"base64://{img_base64}"

        # 构造消息
        message = f"[CQ:image,file={img_url}]\nTags: {tags}\nLink: {post_link}"

        # 编码消息
        encoded_message = await message_codec_package["codec"].decode_CQ_to_message(
            message
        )

        return encoded_message


class Plugin:
    @staticmethod
    def help():
        return danbooru_help.strip()

    @staticmethod
    def description():
        return r"""Danbooru Plugin - 随机图片和标签搜索"""

    @staticmethod
    def create():
        pass

    @staticmethod
    def destroy():
        pass

    @staticmethod
    def before_reload():
        pass

    @staticmethod
    def after_reload():
        pass

    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)

        async def timeout_callback():
            pass

        @plugin_context.timeout(
            15, timeout_callback=timeout_callback
        )  # 增加超时时间以适应标签搜索
        async def handler():
            encoded_message = await message_codec_package["codec"].encode_message_to_CQ(
                message["message"]
            )

            # 匹配 #danbooru 或 #danbooru tag1 tag2 ...
            danbooru_cmd_match = re.match(
                r"^#danbooru(?:\s+(.+))?$", encoded_message.strip()
            )

            # 匹配 #danbooru-page 页码 [tag1 tag2 ...]
            danbooru_page_cmd_match = re.match(
                r"^#danbooru-page\s+(\d+)(?:\s+(.+))?$", encoded_message.strip()
            )

            if danbooru_cmd_match:
                tags = danbooru_cmd_match.group(1)  # 如果有标签，获取标签
                page = None  # 不指定页码，使用随机页码

                try:
                    if tags:
                        log_func("INFO", entity_name, f"用户请求标签搜索: {tags}")
                        await api.send_group_message(
                            message["group_id"],
                            message=f"正在搜索包含标签: {tags} 的图片...",
                        )
                        danbooru_message = await Danbooru.get_random_post_and_encode(
                            tags, page
                        )
                    else:
                        log_func("INFO", entity_name, "用户请求随机图片")
                        await api.send_group_message(
                            message["group_id"], message="正在获取随机图片..."
                        )
                        danbooru_message = await Danbooru.get_random_post_and_encode(
                            None, page
                        )

                except Exception as e:
                    log_func(
                        "ERROR",
                        entity_name,
                        "获取 Danbooru 帖子失败",
                        traceback.format_exc(),
                    )
                    danbooru_message = None

                if danbooru_message:
                    await api.send_group_message(
                        message["group_id"], message=danbooru_message
                    )
                else:
                    if tags:
                        await api.send_group_message(
                            message["group_id"],
                            message=f"未找到包含标签 '{tags}' 的图片",
                        )
                    else:
                        await api.send_group_message(
                            message["group_id"], message="获取 Danbooru 帖子失败"
                        )
                raise plugin_context.SkipFollow()

            elif danbooru_page_cmd_match:
                page_str = danbooru_page_cmd_match.group(1)  # 获取页码
                tags = danbooru_page_cmd_match.group(2)  # 获取可选的标签

                try:
                    page = int(page_str)
                    if page <= 0:
                        page = 1

                    if tags:
                        log_func(
                            "INFO", entity_name, f"用户请求第{page}页标签搜索: {tags}"
                        )
                        await api.send_group_message(
                            message["group_id"],
                            message=f"正在搜索第{page}页包含标签: {tags} 的图片...",
                        )
                    else:
                        log_func("INFO", entity_name, f"用户请求第{page}页随机图片")
                        await api.send_group_message(
                            message["group_id"],
                            message=f"正在获取第{page}页随机图片...",
                        )

                    danbooru_message = await Danbooru.get_random_post_and_encode(
                        tags, page
                    )

                except ValueError:
                    await api.send_group_message(
                        message["group_id"],
                        message="页码必须是一个正整数",
                    )
                    raise plugin_context.SkipFollow()
                except Exception as e:
                    log_func(
                        "ERROR",
                        entity_name,
                        "获取指定页面 Danbooru 帖子失败",
                        traceback.format_exc(),
                    )
                    danbooru_message = None

                if danbooru_message:
                    await api.send_group_message(
                        message["group_id"], message=danbooru_message
                    )
                else:
                    if tags:
                        await api.send_group_message(
                            message["group_id"],
                            message=f"未在第{page}页找到包含标签 '{tags}' 的图片",
                        )
                    else:
                        await api.send_group_message(
                            message["group_id"],
                            message=f"获取第{page}页 Danbooru 帖子失败",
                        )
                raise plugin_context.SkipFollow()

        await handler()
