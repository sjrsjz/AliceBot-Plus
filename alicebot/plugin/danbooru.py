import random
import bs4
import re
import aiohttp
from typing import Optional
from typing import Callable, Any
import traceback
log_func: Callable[[Any], None]
plugin_context: Any # 插件上下文，由插件管理器传入

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)


entity_name = "Danbooru"

danbooru_help = r'''
Danbooru Plugin Help
- #danbooru: Get a random Danbooru post with tags and image URL.
'''

class Danbooru:

    async def get_random_post() -> Optional[dict]:
        """获取一个随机 Danbooru 帖子，返回标签和图片 URL"""
        random_page = random.randint(1, 100)
        url = f"https://danbooru.donmai.us/posts?page={random_page}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                html = await response.text()

                # 使用 Beautiful Soup 解析 HTML
                soup = bs4.BeautifulSoup(html, "html.parser")

                # 找到所有的帖子元素
                posts = soup.select("article.post-preview")
                if not posts:
                    return None

                # 随机选择一个帖子
                post = random.choice(posts)

                # 获取标签
                tags = post.get('data-tags', '')
                if tags:
                    # 处理标签格式
                    tags = bs4.BeautifulSoup(tags, "html.parser").get_text()
                    tags = tags.replace(" ", ",")
                    tags = tags.replace("(", "\\(").replace(")", "\\)")
                    tags = tags.replace("[", "\\[").replace("]", "\\]")
                    tags = tags.replace("{", "\\{").replace("}", "\\}")

                # 获取图片 URL
                img_element = post.select_one("img")
                img_url = ""
                if img_element:
                    # 尝试获取原图URL，或者预览图URL
                    img_url = img_element.get('data-large-file-url') or img_element.get('data-file-url') or img_element.get('src', '')

                # 获取帖子ID和链接
                post_id = post.get('data-id', '')
                post_link = f"https://danbooru.donmai.us/posts/{post_id}" if post_id else ""

                return {
                    "tags": tags,
                    "img_url": img_url,
                    "post_id": post_id,
                    "post_link": post_link
                }

    async def get_random_post_and_encode() -> Optional[str]:
        """获取一个随机 Danbooru 帖子，并返回编码后的消息"""
        post = await Danbooru.get_random_post()
        if not post:
            return None

        tags = post["tags"]
        img_url = post["img_url"]
        post_link = post["post_link"]

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
        return r'''Danbooru Plugin'''

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
        api = onebot_package['api'].OneBotAPI(ws, plugin_context.echo_pool)
        async def timeout_callback():
            pass
        @plugin_context.timeout(5, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            if encoded_message.strip() == "#danbooru":
                try:
                    danbooru_message = await Danbooru.get_random_post_and_encode()
                except Exception as e:
                    log_func('ERROR', entity_name, "获取 Danbooru 帖子失败", traceback.format_exc())
                    danbooru_message = None
                if danbooru_message:
                    await api.send_group_message(message["group_id"], message=encoded_message)
                else:
                    await api.send_group_message(message["group_id"], message="获取 Danbooru 帖子失败")
                raise plugin_context.SkipFollow()

            
        await handler()
