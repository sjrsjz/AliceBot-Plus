# chat.py

import pathlib
import fJson as fjson
import json
import time
import traceback
import base64
import os
import asyncio
import aiohttp
import random
import bs4
from threading import Lock
from typing import Callable, Any, List, Optional, Dict
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import ipaddress
import html2text

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
message_codec_package.load_module("context", hot_reload=True, log_func=log_func)
aibackend_package = moduleloader.ModuleLoader(
    plugin_context.aibackend_package_path, log_func=log_func
)
aibackend_package.load_module("tts", hot_reload=True, log_func=log_func)
aibackend_package.load_module("aipaint", hot_reload=True, log_func=log_func)
aibackend_package.load_module("apikey", hot_reload=True, log_func=log_func)
document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
document_renderer = document_renderer_package.load_module(
    "renderer", hot_reload=True, log_func=log_func
)
prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path, log_func=log_func
)
template = prompt_package.load_module("template", log_func=log_func)
example_prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path / "example" / "character", log_func=log_func
)
example_prompt_package.load_module("Alice", hot_reload=True, log_func=log_func)
example_typeset_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path / "example" / "typeset", log_func=log_func
)
example_typeset_package.load_module("QQBot", hot_reload=True, log_func=log_func)


from autogemini.auto_stream_processor import create_cot_processor, CallbackMsgType
from autogemini.tool_code import DefaultApi
from autogemini import ToolCodeInfo, parse_agent_output
from autogemini.gemini_chat import ChatMessage, MessageRole, MediaFile
from autogemini import APIType

from plugin.util import online_py_executor
from plugin.util import mathworld


entity_name = "Chat"

context_temp_path = pathlib.Path(__file__).parent / "context_temp"
context_temp_path.mkdir(parents=True, exist_ok=True)
context_temp_file = context_temp_path / "context_temp.json"  # 新格式：JSON
context_temp_file_legacy = context_temp_path / "context_temp.fjson"  # 旧格式：fJson
profile_path = pathlib.Path(__file__).parent / "profiles"
profile_path.mkdir(parents=True, exist_ok=True)


def get_default_system_instruction():
    return example_prompt_package["Alice"].character


def get_api_key():
    # return aibackend_package["apikey"].config.key_gemini()
    return aibackend_package["apikey"].config.key_deepseek()


class ContextManager:
    def __init__(self):
        self.group_context = {}
        self.private_context = {}

    def get_group_context(self, group_id):
        if str(group_id) not in self.group_context:
            self.group_context[str(group_id)] = {
                "context": message_codec_package["context"].ContextManager(context=[]),
                "stream_context": message_codec_package["context"].StreamContextManager(
                    context=[],
                    max_length=50,  # 您可以按需调整此值
                ),
                "ai_params": {
                    "system_instruction": get_default_system_instruction(),
                    "trigger": ["Alice"],
                },
            }
        return self.group_context[str(group_id)]

    def get_private_context(self, user_id):
        if str(user_id) not in self.private_context:
            self.private_context[str(user_id)] = {
                "context": message_codec_package[
                    "context"
                ].ContextManager(),  # 会话上下文，由于是私聊，所以无需流式上下文
                "ai_params": {
                    "system_instruction": get_default_system_instruction(),
                    "trigger": ["Alice"],
                },
            }
        return self.private_context[str(user_id)]

    def write_to_temporary_file(self):
        with open(context_temp_file, "w", encoding="utf-8") as f:
            # 数据结构现在自然地包含了 timestamp，直接写入即可
            group_context = {
                str(k): {
                    "context": v["context"].context,
                    "stream_context": (
                        v["stream_context"].context,
                        v["stream_context"].max_length,
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in self.group_context.items()
            }
            private_context = {
                str(k): {"context": v["context"].context, "ai_params": v["ai_params"]}
                for k, v in self.private_context.items()
            }

            # 使用标准JSON格式，性能更好，特别是对于大量图片数据
            context_data = {
                "group_context": group_context,
                "private_context": private_context,
            }

            json.dump(
                context_data, f, ensure_ascii=False, indent=2, separators=(",", ": ")
            )

    def read_from_temporary_file(self):
        context = None

        # 优先尝试读取新的JSON格式文件
        if context_temp_file.exists():
            try:
                with open(context_temp_file, "r", encoding="utf-8") as f:
                    context = json.load(f)
                log_func("INFO", entity_name, "成功读取JSON格式的上下文文件")
            except Exception as e:
                log_func("ERROR", entity_name, f"读取JSON格式上下文文件失败: {e}")

        # 如果JSON文件不存在或读取失败，尝试迁移旧的fJson文件
        if context is None and context_temp_file_legacy.exists():
            try:
                log_func(
                    "INFO", entity_name, "检测到旧版fJson格式，开始迁移到JSON格式..."
                )
                with open(context_temp_file_legacy, "r", encoding="utf-8") as f:
                    context = fjson.decode(f.read())

                # 迁移成功后，保存为新的JSON格式
                if context is not None:
                    log_func(
                        "INFO", entity_name, "fJson读取成功，正在转换为JSON格式..."
                    )

                    # 临时存储数据以便写入
                    temp_group_context = {}
                    temp_private_context = {}

                    # 处理群聊上下文
                    for k, v in context["group_context"].items():
                        upgraded_main_context = []
                        for i, msg in enumerate(v["context"]):
                            if "timestamp" not in msg:
                                msg["timestamp"] = time.time() - (99999 - i)
                            upgraded_main_context.append(msg)

                        upgraded_stream_context = []
                        stream_context_data = v.get("stream_context", ([], 50))
                        for msg in stream_context_data[0]:
                            if "timestamp" not in msg:
                                if "time" in msg and isinstance(msg["time"], str):
                                    try:
                                        msg["timestamp"] = time.mktime(
                                            time.strptime(msg["time"])
                                        )
                                    except ValueError:
                                        msg["timestamp"] = time.time() - 99999
                                else:
                                    msg["timestamp"] = time.time() - 99999
                            upgraded_stream_context.append(msg)

                        temp_group_context[str(k)] = {
                            "context": message_codec_package["context"].ContextManager(
                                context=upgraded_main_context
                            ),
                            "stream_context": message_codec_package[
                                "context"
                            ].StreamContextManager(
                                context=upgraded_stream_context,
                                max_length=stream_context_data[1],
                            ),
                            "ai_params": v["ai_params"],
                        }

                    # 处理私聊上下文
                    for k, v in context["private_context"].items():
                        upgraded_private_context = []
                        for i, msg in enumerate(v["context"]):
                            if "timestamp" not in msg:
                                msg["timestamp"] = time.time() - (99999 - i)
                            upgraded_private_context.append(msg)

                        temp_private_context[str(k)] = {
                            "context": message_codec_package["context"].ContextManager(
                                context=upgraded_private_context
                            ),
                            "ai_params": v["ai_params"],
                        }

                    # 设置临时上下文
                    self.group_context = temp_group_context
                    self.private_context = temp_private_context

                    # 立即保存为JSON格式
                    self.write_to_temporary_file()

                    # 删除旧的fJson文件
                    try:
                        context_temp_file_legacy.unlink()
                        log_func("INFO", entity_name, "成功删除旧版fJson文件，迁移完成")
                    except Exception as e:
                        log_func(
                            "WARN",
                            entity_name,
                            f"删除旧版fJson文件失败，但不影响使用: {e}",
                        )

                    log_func("INFO", entity_name, "成功迁移到JSON格式，性能将显著提升")
                    return  # 迁移完成，直接返回

            except Exception as e:
                log_func("ERROR", entity_name, f"迁移fJson文件失败: {e}")

        # 如果没有任何文件或迁移失败，创建新的空上下文
        if context is None:
            log_func("INFO", entity_name, "未找到现有上下文文件，创建新的空上下文")
            self.group_context = {}
            self.private_context = {}
            return

        # 处理读取到的JSON格式数据
        self.group_context = {}
        self.private_context = {}

        # 处理群聊上下文
        for k, v in context["group_context"].items():
            upgraded_main_context = []
            for i, msg in enumerate(v["context"]):
                if "timestamp" not in msg:
                    msg["timestamp"] = time.time() - (99999 - i)
                upgraded_main_context.append(msg)

            upgraded_stream_context = []
            stream_context_data = v.get("stream_context", ([], 50))
            for msg in stream_context_data[0]:
                if "timestamp" not in msg:
                    if "time" in msg and isinstance(msg["time"], str):
                        try:
                            msg["timestamp"] = time.mktime(time.strptime(msg["time"]))
                        except ValueError:
                            msg["timestamp"] = time.time() - 99999
                    else:
                        msg["timestamp"] = time.time() - 99999
                upgraded_stream_context.append(msg)

            self.group_context[str(k)] = {
                "context": message_codec_package["context"].ContextManager(
                    context=upgraded_main_context
                ),
                "stream_context": message_codec_package["context"].StreamContextManager(
                    context=upgraded_stream_context,
                    max_length=stream_context_data[1],
                ),
                "ai_params": v["ai_params"],
            }

        # 处理私聊上下文
        for k, v in context["private_context"].items():
            upgraded_private_context = []
            for i, msg in enumerate(v["context"]):
                if "timestamp" not in msg:
                    msg["timestamp"] = time.time() - (99999 - i)
                upgraded_private_context.append(msg)

            self.private_context[str(k)] = {
                "context": message_codec_package["context"].ContextManager(
                    context=upgraded_private_context
                ),
                "ai_params": v["ai_params"],
            }

    async def get_profile(self, user_id):
        group_profile_file = profile_path / f"user_{user_id}_profile.json"
        if not group_profile_file.exists():
            with open(group_profile_file, "w", encoding="utf-8") as f:
                f.write(fjson.encode({}))
        try:
            with open(group_profile_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log_func(
                "WARN",
                entity_name,
                f"Failed to get profile: {e}",
            )
            return None

    async def build_context(
        self,
        api,
        main_context: List[Dict],  # AI与用户的核心对话历史
        user_id: int,
        user_message_id: int,
        user_request: str,
        stream_context: Any,  # 群聊的流式消息历史
        group_id: int = None,
    ) -> tuple[List[Dict], str]:
        """
        通过按时间顺序合并主上下文和流式上下文来构建一个统一的、时序正确的对话历史。
        """
        final_context_for_ai = []

        async def get_autosaves_file_informations():
            files = os.listdir(profile_path)
            result = []
            for file in files:
                file_path = profile_path / file
                file_size = os.path.getsize(file_path)
                file_modify_time = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(file_path))
                )
                file_create_time = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(file_path))
                )
                result.append(
                    {
                        "filename": file,
                        "size": file_size,
                        "modify_time": file_modify_time,
                        "create_time": file_create_time,
                    }
                )
            return result

        autosaves = await get_autosaves_file_informations()
        autosave_str = "<reactAgentSegmentHeader>think</reactAgentSegmentHeader>\n# here are my files saved in the past, I will use them as datebase to answer questions:\n"
        autosave_str += "filename\n --- \n"
        for autosave in autosaves:
            autosave_str += f"{autosave['filename']}\n"

        final_context_for_ai.insert(
            0,
            {
                "role": "assistant",
                "content": autosave_str,
            },
        )

        if group_id:
            try:
                group_member_list = await api.get_member_list(group_id)
            except:
                group_member_list = []
            if len(group_member_list) <= 200:
                formatted_member_list = (
                    "```users\ncard | nickname | gender | qq\n --- | --- | --- | ---\n"
                )
                for member in group_member_list:
                    formatted_member_list += f"{member['card']} | {member['nickname']} | {member['sex']} | {member['user_id']}\n"
                formatted_member_list += "```"
            elif len(group_member_list) <= 500:
                formatted_member_list = "```users\nnickname | qq\n --- | ---\n"
                for member in group_member_list:
                    nickname = (
                        member["card"] if member["card"] != None else member["nickname"]
                    )
                    formatted_member_list += f"{nickname} | {member['user_id']}\n"
                formatted_member_list += "```"
            else:
                formatted_member_list = "```users\nmember count exceeds 500\n```"

            final_context_for_ai.insert(
                0,
                {
                    "role": "user",
                    "content": f"<reactAgentSegmentHeader>user_list</reactAgentSegmentHeader>{formatted_member_list}",
                },
            )

        # --- 步骤 2: 合并并排序所有对话历史 ---

        merged_history = []

        # 2a. 添加主对话历史 (AI和用户的直接互动)
        merged_history.extend(main_context)

        # 2b. 添加流式群聊历史
        for item in stream_context.get_message():
            # 将 stream_context 的消息格式转换为与 main_context 一致的格式
            merged_item = {
                "role": "user",  # 所有群聊消息都视为'user'发言
                "content": f"[{item['name']}]: {item['content']}",
                "timestamp": item["timestamp"],
                # 保留原始信息以便调试
                "original_stream_item": True,
            }

            # 重要：如果流式消息中包含媒体文件，需要保留它们
            if "media_files" in item and item["media_files"]:
                merged_item["media_files"] = item["media_files"]
                # 记录调试信息
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Stream message contains {len(item['media_files'])} media files",
                )

            merged_history.append(merged_item)

        # 2c. 按时间戳对所有历史记录进行排序
        # 这是实现时序正确的关键一步
        merged_history.sort(key=lambda x: x.get("timestamp", 0.0))

        # 2d. 将排序后的历史格式化并添加到最终上下文中
        for item in merged_history:
            # 忽略没有内容的无效条目
            if not item.get("content"):
                continue

            # 构建上下文项目，保留媒体文件信息
            context_item = {"role": item["role"], "content": item["content"]}

            # 重要：如果项目包含媒体文件，需要保留它们
            if "media_files" in item and item["media_files"]:
                context_item["media_files"] = item["media_files"]
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Preserving {len(item['media_files'])} media files in final context",
                )

            final_context_for_ai.append(context_item)

        # --- 步骤 3: 添加当前用户的最终请求 ---
        # 这必须是列表中的最后一条消息。
        user_info = await api.get_stranger_info(user_id)
        user_sex = user_info.get("sex", "unknown")
        user_name = user_info.get("nickname", "unknown")

        # 用于存储到历史记录的完整请求头（保留了所有细节）
        real_request_for_history = (
            f"## Name: {user_name} (use `[CQ:at,qq={user_id}]` to mention)\n"
            f"## Time: {time.asctime()}\n"
            f"## User Sex: {user_sex}\n"
            f"## User Message ID: `[CQ:reply,id={user_message_id}]`\n"
            f"## User Message:\n{user_request}\n"
        )

        # 传递给模型的当前用户提示（更简洁，突出重点）
        current_user_profile = await self.get_profile(user_id)
        current_user_message_content = (
            f"# Current User (Talking to A.I.(you) now):\n"
            f"## Name: {user_name} (use `[CQ:at,qq={user_id}]` to mention)\n"
            f"---(User Profile Start)---\n{current_user_profile}"
            f"---(User Profile End)---\n"
            f"## Time: {time.asctime()}\n"
            f"## User Sex: {user_sex}\n"
            f"## User Message ID: `[CQ:reply,id={user_message_id}]`\n"
            f"## User Message:\n{user_request}\n"
        )

        final_context_for_ai.append(
            {"role": "user", "content": current_user_message_content}
        )

        return final_context_for_ai, real_request_for_history


class Danbooru:
    """
    通过并发请求优化了Danbooru帖子的获取过程。
    首先获取帖子列表，然后并发获取每个帖子的详细信息（如高清图URL）。
    """

    @staticmethod
    async def _fetch_post_details(
        session: aiohttp.ClientSession, post: bs4.element.Tag
    ) -> Optional[Dict]:
        """
        一个辅助方法，用于异步获取单个帖子的详细信息。
        这是并发执行的核心单元。

        参数:
            session: aiohttp客户端会话。
            post: 从列表页解析出的单个帖子的BeautifulSoup Tag对象。
        """
        post_id = post.get("data-id")
        if not post_id:
            return None  # 如果没有post_id，则跳过

        post_tags = post.get("data-tags", "")
        post_link = f"https://danbooru.donmai.us/posts/{post_id}"

        img_url = ""
        # 尝试从详情页获取原图 (这是网络IO密集型操作)
        log_func("INFO", entity_name, f"开始获取帖子详情: {post_link}")
        try:
            async with session.get(post_link) as detail_response:
                if detail_response.status == 200:
                    detail_html = await detail_response.text()
                    detail_soup = bs4.BeautifulSoup(detail_html, "html.parser")
                    # 查找图片元素的逻辑保持不变
                    img_element = detail_soup.select_one(
                        "section.image-container picture img"
                    )
                    if not img_element:
                        img_element = detail_soup.select_one(
                            "section.image-container img"
                        )
                    if img_element:
                        img_url = img_element.get("src", "")
                        if not img_url:
                            img_url = img_element.get(
                                "data-large-file-url"
                            ) or img_element.get("data-file-url")
                else:
                    log_func(
                        "WARN",
                        entity_name,
                        f"访问详情页失败 {post_link}，状态码: {detail_response.status}",
                    )
        except Exception as e:
            log_func("ERROR", entity_name, f"获取帖子详情页异常 {post_link}: {e}")

        # 如果详情页获取失败，回退到从列表页解析预览图的逻辑
        if not img_url:
            log_func(
                "INFO", entity_name, f"无法从详情页获取图片，尝试从列表页获取 {post_id}"
            )
            source_element = post.select_one("source")
            if source_element and (srcset := source_element.get("srcset")):
                # srcset 通常包含多个尺寸，取最后一个（通常是最大的）
                img_url = srcset.split(",")[-1].strip().split(" ")[0]
            if not img_url:
                img_element = post.select_one("img")
                if img_element:
                    img_url = (
                        img_element.get("data-large-file-url")
                        or img_element.get("data-file-url")
                        or img_element.get("src", "")
                    )

        if not img_url:
            log_func("WARN", entity_name, f"最终未能找到帖子 {post_id} 的图片URL")
            return None

        log_func(
            "INFO",
            entity_name,
            f"成功获取 Post ID: {post_id}, Image URL: {img_url[:50]}...",
        )
        return {
            "tags": post_tags,
            "img_url": img_url,
            "post_id": post_id,
            "post_link": post_link,
        }

    @staticmethod
    async def get_random_post(
        tags: Optional[str] = None, page: Optional[int] = None
    ) -> Optional[List[Dict]]:
        """
        并发获取Danbooru帖子列表，返回所有解析到的图片和标签等信息。

        参数:
            tags: 可选，指定标签查询，多个标签用空格分隔。
            page: 可选，指定页码，默认为随机页码。
        """
        base_url = "https://danbooru.donmai.us/posts"

        # --- 步骤 1: 获取帖子列表页 (单次请求) ---
        if page is None:
            page = random.randint(1, 100)
            log_func("INFO", entity_name, f"随机页面: {page}")
        else:
            log_func("INFO", entity_name, f"指定页面: {page}")

        params = {"page": page}
        if tags:
            # Danbooru API 限制 tag 数量，这里在前端进行提醒
            if len(tags.split()) > 2:
                log_func(
                    "WARN", entity_name, "Danbooru 建议最多使用两个标签以避免422错误。"
                )
            params["tags"] = tags
            log_func("INFO", entity_name, f"按标签搜索: {tags}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(base_url, params=params) as response:
                    if response.status == 422:
                        log_func(
                            "ERROR",
                            entity_name,
                            "Danbooru 422错误，可能是tag过多。AI应限制最多只能使用两个tag。",
                        )
                        raise Exception(
                            "422 Unprocessable Entity: Too many tags. Please use at most two tags for Danbooru search."
                        )
                    response.raise_for_status()  # 对所有非2xx状态码抛出异常

                    html = await response.text()
                    soup = bs4.BeautifulSoup(html, "html.parser")
                    posts_on_page = soup.select("article.post-preview")

                    if not posts_on_page:
                        log_func("ERROR", entity_name, "没有找到帖子元素")
                        raise Exception(
                            "No posts found on Danbooru for the given tags and page."
                        )

                    # --- 步骤 2: 为每个帖子创建并发任务 ---
                    tasks = [
                        Danbooru._fetch_post_details(session, post)
                        for post in posts_on_page
                    ]

                    # --- 步骤 3: 并发执行所有任务并等待结果 ---
                    log_func(
                        "INFO",
                        entity_name,
                        f"找到 {len(tasks)} 个帖子, 开始并发获取详情...",
                    )
                    results_with_none = await asyncio.gather(
                        *tasks, return_exceptions=True
                    )

                    # --- 步骤 4: 处理结果 ---
                    final_results = []
                    for res in results_with_none:
                        if isinstance(res, Exception):
                            log_func("ERROR", entity_name, f"一个并发任务失败: {res}")
                        elif res is not None:
                            final_results.append(res)

                    log_func(
                        "INFO",
                        entity_name,
                        f"成功获取 {len(final_results)} 个帖子的详细信息。",
                    )
                    return final_results

            except aiohttp.ClientResponseError as e:
                # 重新组织异常处理，使其更清晰
                if e.status == 422:
                    log_func(
                        "ERROR",
                        entity_name,
                        "Danbooru 422错误，可能是tag过多。AI应限制最多只能使用两个tag。",
                    )
                    raise Exception(
                        "422 Unprocessable Entity: Too many tags. Please use at most two tags for Danbooru search."
                    )
                else:
                    log_func("ERROR", entity_name, f"获取帖子列表失败: {e}")
                    raise Exception(f"Failed to fetch posts list: {e}")
            except Exception as e:
                log_func("ERROR", entity_name, f"Danbooru请求异常: {e}")
                raise Exception(f"Danbooru request error: {e}")


def get_agent_tool_codes() -> List[ToolCodeInfo]:
    """Defines the tools available to the agent in the required format."""
    return [
        ToolCodeInfo(
            name="search_on_web",
            description="Searches the web for up-to-date or unknown information. Use this if you cannot answer from your own knowledge.",
            detail="Performs a web search using the Bing engine and returns a summary of the results.",
            args={"query": "A clear and concise search query string."},
        ),
        ToolCodeInfo(
            name="get_webpage_content",
            description="Retrieves the full text content from a specific webpage URL.",
            detail="Given a URL, this tool will open it and return all readable text in Markdown format.",
            args={
                "url": "The complete and valid URL of the webpage (e.g., 'https://www.example.com')."
            },
        ),
        ToolCodeInfo(
            name="execute_python",
            description="Executes Python code in a sandboxed environment for calculations, data manipulation, or algorithmic tasks. Cannot access the network or local files.",
            detail="The final line of the code should be an expression or a `print()` call to produce an output.",
            args={"code": "A string containing valid Python code to be executed."},
        ),
        ToolCodeInfo(
            name="http_request",
            description="Makes a generic HTTP request (e.g., GET, POST) to a specified URL. Use this for interacting with web APIs that do not have a dedicated tool.",
            detail="Allows you to send customized HTTP requests. You can specify the method, headers, URL parameters, and a JSON body. Returns the text content of the response. **Security Warning:** Do not include secret API keys or other credentials in your calls unless explicitly instructed and acknowledged by the user. Requests to local network addresses are forbidden.",
            args={
                "method": "The HTTP method to use (e.g., 'GET', 'POST', 'PUT', 'DELETE'). Must be uppercase.",
                "url": "The full URL of the API endpoint to call.",
                "params": "Optional. A dictionary of URL parameters for GET requests (e.g., {'query': 'value'}).",
                "headers": "Optional. A dictionary of HTTP headers to send (e.g., {'Content-Type': 'application/json', 'Authorization': 'Bearer ...'}).",
                "json_body": "Optional. A dictionary that will be automatically converted to a JSON string and sent as the request body, typically for POST or PUT requests.",
            },
        ),
        ToolCodeInfo(
            name="compute_with_wolfram",
            description="Solves complex mathematical problems, answers scientific questions, and provides structured data using the Wolfram Alpha engine.",
            detail="Ideal for calculus, algebra, chemistry, physics, and knowledge-based queries.",
            args={
                "expression": "The mathematical expression or natural language query for Wolfram Alpha."
            },
        ),
        ToolCodeInfo(
            name="read_from_file",
            description="Reads the content of one or more files that you have previously saved.",
            detail="You can provide multiple filenames separated by a pipe character ('|').",
            args={
                "filenames": "The name of the file(s) to read, e.g., 'notes.txt' or 'plan.md|data.json'."
            },
        ),
        ToolCodeInfo(
            name="write_to_file",
            description="Writes or overwrites content to a specified file in your personal storage.",
            detail="This tool is useful for saving your thought processes, plans, code snippets, or long-term information that the user asks you to remember. If the file already exists, it will be completely replaced with the new content.",
            args={
                "filename": "The name of the file to write to, e.g., 'my_notes.txt' or 'code_snippet.py'.",
                "content": "The text content to write into the file.",
            },
        ),
        ToolCodeInfo(
            name="search_on_mathworld",
            description="Searches Wolfram MathWorld for detailed definitions, theorems, and formulas related to a specific mathematical concept.",
            detail="This is a specialized tool for deep mathematical research.",
            args={
                "query": "The mathematical term or concept to look up (e.g., 'Eigenvalue' or 'Riemann Hypothesis')."
            },
        ),
        ToolCodeInfo(
            name="search_on_danbooru",
            description="Searches for a random SFW (safe-for-work) or NSFW (not-safe-for-work) anime-style image on the Danbooru image board. Use this when the user asks for a 'random picture', 'anime image', or something similar.",
            detail="You can provide tags to narrow the search. **IMPORTANT: You can only use a maximum of TWO (2) tags.** Tags with multiple words must be joined by an underscore (e.g., 'blue_hair'). The tool returns a direct URL to the image.",
            args={
                "tags": "A string containing one or two tags, separated by a space. Example: '1girl blue_hair'. Leave empty for a completely random image. ONLY supports **ENGLISH** tags.",
            },
        ),
        ToolCodeInfo(
            name="ban_user",
            description="Bans a user from the current group for a specified duration (Group Admin Only).",
            detail="This tool allows you to temporarily ban a user from the group. The ban duration is limited to 1-10 minutes. Use this when a user violates group rules or behaves inappropriately.",
            args={
                "user_id": "The QQ number of the user to ban (string or integer).",
                "minutes": "The duration of the ban in minutes (1-10 minutes, integer).",
                "reason": "The reason for the ban (optional, for logging purposes).",
            },
        ),
        ToolCodeInfo(
            name="onebot_v11_api_call",
            description="Makes a direct OneBot v11 API call to interact with the chat platform.",
            detail="This tool allows you to call any OneBot v11 API endpoint directly. Use this for advanced interactions not covered by other tools.",
            args={
                "json_data": "A dictionary representing the JSON data to send in the OneBot v11 API call. Example: {'action': 'send_msg', 'params': {'group_id': 123456, 'message': 'Hello!'}}"
            },
        ),
    ]


async def create_agent_api_handler(group_id: int = None, api=None) -> DefaultApi:
    """Creates the API handler that maps tool names to their actual implementation."""

    async def api_handler(method_name: str, *args, **kwargs) -> Any:
        log_func(
            "INFO",
            entity_name,
            f"Agent Tool Call: {method_name} with args: {args}, kwargs: {kwargs}",
        )

        # Prefer kwargs, but fallback to args for simpler tool definitions
        first_arg = next(iter(kwargs.values()), None) or (args[0] if args else None)
        if first_arg is None:
            return f"[Error] Tool '{method_name}' was called without any arguments."

        try:
            if method_name == "search_on_web":
                return await document_renderer_package["renderer"].web_search(
                    await plugin_context.bot_entity.browser.get_browser(),
                    first_arg,
                    20,
                    "Bing",
                )
            elif method_name == "get_webpage_content":
                return await document_renderer_package["renderer"].get_webpage(
                    await plugin_context.bot_entity.browser.get_browser(),
                    first_arg,
                    only_text=True,
                    max_token=4096,
                )
            elif method_name == "execute_python":
                return await online_py_executor.execute_python_code(first_arg)
            elif method_name == "compute_with_wolfram":
                return await document_renderer_package[
                    "renderer"
                ].wolfram_alpha.wolfram_alpha_compute_without_image(first_arg)
            elif method_name == "read_from_file":
                files = first_arg.split("|")
                result_dict = {}
                for file in files:
                    file_name = file.strip()
                    try:
                        with open(profile_path / file_name, "r", encoding="utf-8") as f:
                            result_dict[file_name] = f.read()
                    except Exception as e:
                        result_dict[file_name] = (
                            f"[System] Failed to read file '{file_name}': {e}"
                        )
                return result_dict
            elif method_name == "write_to_file":
                filename = kwargs.get("filename")
                content = kwargs.get("content")
                if (
                    not filename or content is None
                ):  # content可以是空字符串，所以要判断None
                    return "[Error] `write_to_file` tool requires both 'filename' and 'content' arguments."

                # 使用之前定义好的 profile_path
                file_path = profile_path / filename
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                log_func("INFO", entity_name, f"Successfully wrote to file: {filename}")
                return f"[Success] Content has been saved to '{filename}'."
            elif method_name == "search_on_mathworld":
                result = await mathworld.get_content_from_results(first_arg, n=3)
                return result or "No results found on MathWorld."
            elif method_name == "search_on_danbooru":
                tags = first_arg
                log_func(
                    "INFO",
                    entity_name,
                    f"Agent is searching Danbooru with tags: {tags}",
                )
                try:
                    post_data = await Danbooru.get_random_post(tags=tags)
                    return post_data
                except Exception as e:
                    log_func("ERROR", entity_name, f"search_on_danbooru error: {e}")
                    return f"[Danbooru Error] {e}"
            elif method_name == "http_request":
                method = kwargs.get("method")
                url = kwargs.get("url")

                if not method or not url:
                    return "[HTTP Request Error] 'method' and 'url' are required arguments."

                if _is_disallowed_url(url):
                    return f"[HTTP Request Error] Access to the URL '{url}' is forbidden for security reasons."

                params = kwargs.get("params")
                headers = kwargs.get("headers")
                json_body = kwargs.get("json_body")

                try:
                    async with aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as session:
                        async with session.request(
                            method=method.upper(),
                            url=url,
                            params=params,
                            headers=headers,
                            json=json_body,
                        ) as response:
                            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
                            # 注意：如果API返回的是二进制数据（如图片），.text()可能会出错。
                            # 目前假设API返回文本（如JSON）。
                            return await response.text()
                except asyncio.TimeoutError:
                    return f"[HTTP Request Error] The request to '{url}' timed out."
                except aiohttp.ClientResponseError as e:
                    return f"[HTTP Request Error] Status {e.status}: {e.message}. URL: {url}"
                except aiohttp.ClientError as e:
                    return f"[HTTP Request Error] A client-side error occurred: {e}. URL: {url}"
                except Exception as e:
                    return f"[HTTP Request Error] An unexpected error occurred: {e}. URL: {url}"
            elif method_name == "ban_user":
                # 获取参数
                user_id = kwargs.get("user_id")
                minutes = kwargs.get("minutes", 1)
                reason = kwargs.get("reason", "Violation of group rules")

                # 参数验证
                if not user_id:
                    return "[Ban User Error] 'user_id' is a required argument."

                if not group_id:
                    return "[Ban User Error] This tool can only be used in group chats."

                if not api:
                    return "[Ban User Error] API instance not available."

                try:
                    # 确保user_id是字符串或整数
                    user_id = str(user_id)
                    # 确保minutes是整数且在合理范围内
                    minutes = int(minutes)
                    minutes = max(1, min(10, minutes))  # 限制在1-10分钟之间

                    # 执行ban操作
                    await api.set_group_ban(group_id, user_id, minutes * 60)

                    log_func(
                        "INFO",
                        entity_name,
                        f"User {user_id} banned for {minutes} minutes in group {group_id}. Reason: {reason}",
                    )

                    return f"User {user_id} has been banned for {minutes} minutes. Reason: {reason}"

                except ValueError:
                    return "[Ban User Error] 'minutes' must be a valid integer between 1 and 10."
                except Exception as e:
                    log_func(
                        "ERROR",
                        entity_name,
                        f"Error banning user {user_id}: {e}",
                    )
                    return f"[Ban User Error] Failed to ban user: {e}"
            elif method_name == "onebot_v11_api_call":
                json_data = first_arg
                if not isinstance(json_data, dict):
                    return (
                        "[OneBot v11 API Call Error] 'json_data' must be a dictionary."
                    )

                if not api:
                    return "[OneBot v11 API Call Error] API instance not available."

                try:
                    response = await api.direct(json_data)
                    return str(response)
                except Exception as e:
                    log_func(
                        "ERROR",
                        entity_name,
                        f"Error in OneBot v11 API call: {e}",
                    )
                    return (
                        f"[OneBot v11 API Call Error] Failed to execute API call: {e}"
                    )
            else:
                return f"[Error] Unknown tool called: {method_name}"
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Error executing tool '{method_name}': {traceback.format_exc()}",
            )
            return f"[Error] An exception occurred while executing tool '{method_name}': {e}"

    return DefaultApi(api_handler)


def _is_disallowed_url(url: str) -> bool:
    """Checks if a URL points to a disallowed address (e.g., localhost, private network)."""
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if not hostname:
            return True  # Not a valid hostname

        # Resolve hostname to IP address to check if it's a private/local IP
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_unspecified
    except ValueError:
        # If hostname is not a valid IP, it's a domain name.
        # We perform a basic check for common local-only names.
        if hostname in ["localhost", "host.docker.internal"]:
            return True
        # A more robust solution might involve DNS resolution here, but that adds latency.
        # For now, we assume public domain names are safe.
        return False
    except Exception:
        # Any other parsing error
        return True


def convert_history_to_chat_messages(history: List[dict]) -> List[ChatMessage]:
    """Converts the plugin's dictionary-based history to the agent's ChatMessage format."""

    # AutoGemini支持的媒体类型
    SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

    chat_messages: List[ChatMessage] = []
    for item in history:
        role = None
        if item.get("role") == "user":
            role = MessageRole.USER
        elif item.get("role") == "assistant":
            role = (
                MessageRole.ASSISTANT
            )  # The agent's own responses are tagged as 'model'

        if role and "content" in item:
            chat_message = ChatMessage(role=role, content=str(item["content"]))

            # 处理可能包含的图片信息（向前兼容）
            # 检查content中是否包含图片base64数据或其他媒体信息
            if "media_files" in item:
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Processing {len(item['media_files'])} media files from history item",
                )
                # 新格式：直接包含媒体文件信息
                for i, media_info in enumerate(item["media_files"]):
                    try:
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"Processing media file {i}: {media_info.keys()}",
                        )
                        if "data" in media_info and "mime_type" in media_info:
                            mime_type = media_info["mime_type"]

                            # 检查媒体类型是否被支持
                            if mime_type not in SUPPORTED_MEDIA_TYPES:
                                log_func(
                                    "WARN",
                                    entity_name,
                                    f"Skipping unsupported media type: {mime_type}",
                                )
                                continue

                            # 如果是base64编码的数据，需要解码
                            media_data = media_info["data"]
                            log_func(
                                "DEBUG",
                                entity_name,
                                f"Media data type: {type(media_data)}, length: {len(media_data) if isinstance(media_data, str) else 'not string'}",
                            )

                            if isinstance(media_data, str):
                                import base64

                                try:
                                    media_data = base64.b64decode(media_data)
                                    log_func(
                                        "DEBUG",
                                        entity_name,
                                        f"Successfully decoded base64, binary length: {len(media_data)}",
                                    )
                                except Exception as decode_error:
                                    log_func(
                                        "ERROR",
                                        entity_name,
                                        f"Base64 decode failed: {decode_error}",
                                    )
                                    continue

                            media_file = MediaFile(data=media_data, mime_type=mime_type)
                            chat_message.media_files.append(media_file)
                            log_func(
                                "INFO",
                                entity_name,
                                f"Successfully added media file to chat message: {mime_type}",
                            )
                        else:
                            log_func(
                                "WARN",
                                entity_name,
                                f"Media file missing data or mime_type: {media_info.keys()}",
                            )
                    except Exception as e:
                        log_func(
                            "WARN",
                            entity_name,
                            f"Failed to process media file in history: {e}",
                        )
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"Media file processing traceback: {traceback.format_exc()}",
                        )

            chat_messages.append(chat_message)

    return chat_messages


async def extract_media_from_message(
    message_data: List[dict],
) -> tuple[str, List[dict]]:
    """
    从消息中提取文本和媒体文件。
    返回: (纯文本内容, 媒体文件列表)
    """
    text_content = ""
    media_files = []

    for item in message_data:
        if item["type"] == "text":
            text_content += item["data"]["text"]
        elif item["type"] == "image":
            try:
                media_info = {}

                if "base64" in item["data"]:
                    # 处理base64编码的图片
                    img_base64 = item["data"]["base64"]
                    img_data = base64.b64decode(img_base64)

                    # 尝试检测MIME类型
                    if img_data.startswith(b"\xff\xd8\xff"):
                        mime_type = "image/jpeg"
                    elif img_data.startswith(b"\x89PNG\r\n\x1a\n"):
                        mime_type = "image/png"
                    elif img_data.startswith(b"GIF8"):
                        mime_type = "image/gif"
                    elif img_data.startswith(b"RIFF") and b"WEBP" in img_data[:12]:
                        mime_type = "image/webp"
                    else:
                        mime_type = "image/jpeg"  # 默认假设为jpeg

                    media_info = {
                        "data": img_base64,  # 保持base64格式便于存储
                        "mime_type": mime_type,
                        "source": "base64",
                    }

                    log_func(
                        "DEBUG",
                        entity_name,
                        f"Extracted image: {mime_type}, base64 length: {len(img_base64)}",
                    )

                elif "url" in item["data"]:
                    # 处理URL图片
                    url = item["data"]["url"]
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(url, timeout=30) as response:
                                if response.status == 200:
                                    img_data = await response.read()
                                    img_base64 = base64.b64encode(img_data).decode()

                                    content_type = response.headers.get(
                                        "Content-Type", "image/jpeg"
                                    )

                                    media_info = {
                                        "data": img_base64,
                                        "mime_type": content_type,
                                        "source": "url",
                                        "url": url,
                                    }
                                else:
                                    log_func(
                                        "WARN",
                                        entity_name,
                                        f"Failed to download image from {url}, status: {response.status}",
                                    )
                                    continue
                    except Exception as e:
                        log_func(
                            "WARN",
                            entity_name,
                            f"Failed to download image from {url}: {e}",
                        )
                        continue

                if media_info:
                    media_files.append(media_info)

            except Exception as e:
                log_func("WARN", entity_name, f"Failed to process image: {e}")
                continue
        elif item["type"] == "at":
            # 保留@信息
            text_content += f"[CQ:at,qq={item['data']['qq']}]"
        else:
            # 其他类型的消息，转换为CQ码格式
            cq_code = f"[CQ:{item['type']},"
            for key, value in item["data"].items():
                cq_code += f"{key}={value},"
            cq_code = cq_code.rstrip(",") + "]"
            text_content += cq_code

    return text_content.strip(), media_files


# --- END AGENT HELPER FUNCTIONS ---


CUSTOM_TAGS_PROMPT = """
Your final response must be formatted using ONLY the tags listed below.
This allows your response to be displayed correctly and for special actions to be executed.

---
### **Part 1: Standard HTML Formatting Tags**
Use these for structuring your text response.

- `<p>...</p>`: For standard paragraphs.
- `<br>`: For line breaks, since your output will be rendered as HTML., `<br>` is important for separating lines.
- `<h1>, <h2>, <h3>`: For section headings.
- `<strong>, <b>`: For strong emphasis.
- `<em>, <i>`: For general emphasis.
- `<ul>, <ol>, <li>`: For lists.
- `<code>, <pre>`: For code blocks.
- `<a href="...">...</a>`: For hyperlinks.
- `<hr>`: For separate multiple sections and send them one by one. For example, "this is the first message.<hr>this is the second message." then the two parts will be sent as two separate messages.

---
### **Part 2: Special Action Tags**
Sometimes you may display rich media content using these tags to perform specific actions. Do NOT use them for simple text formatting.

**1. Text-to-Speech:**
   - **Tag:** `<tts emotion="...">...</tts>`
   - **Purpose:** Converts the enclosed text into a voice message.
   - **Attributes:** `emotion` (optional) - can be "happy", "sad", "excited", etc., to influence the voice tone.
   - **Example:** `<tts emotion="excited">你好！</tts>`
   - **Note:** Since the TTS costs money, use it only when necessary.

**2. Text-to-Image:**
   - **Tag:** `<tti style="..." orientation="...">...</tti>`
   - **Purpose:** Generates an image based on the enclosed English prompt.
   - **Attributes:**
     - `style`: "anime" (default) or "photo".
     - `orientation`: "wide" (default) or "tall".
   - **Example:** `<tti style="anime" orientation="tall">1girl, white hair, cat ears, looking at viewer</tti>`
   - **Note:** Text-to-Image is not `tool_code`, you should only use it in `response` block.

**3. Wolfram|Alpha Calculation Display:**
   - **Tag:** `<wolfram>...</wolfram>`
   - **Purpose:** Computes the enclosed query using Wolfram|Alpha and displays the result as an image.
   - **Example:** `<wolfram>integrate x^2 dx from 0 to 1</wolfram>`

**4. Markdown to Image Rendering:**
   - **Tag:** `<document-render>...</document-render>`
   - **Purpose:** Renders the enclosed Markdown content or HTML content as an image. Use this for complex tables, formulas, or layouts that standard HTML can't handle.
   - **Example:** `<document-render>| Header 1 | Header 2 |\n|---|---|\n| Cell 1 | Cell 2 |</document-render>`

**5. Display Image from URL:**
   - **Tag:** `<image src="..." />`
   - **Purpose:** Downloads an image from a public URL and displays it directly in the chat.
   - **Attributes:** `src` - The full, direct URL to the image file (e.g., .png, .jpg, .gif).
   - **Example:** `<image src="https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png" />`

**6. At or Mention a User:**
    - **Tag:** `<at qq="..." />`
    - **Purpose:** Mentions a user in the group chat.
    - **Attributes:** `qq` - The QQ number of the user to mention.
    - **Example:** `<at qq="123456789" />`

---
### **Final Instruction**
Your entire final response must be composed using a sequence of the tags described above.

# Remember: ALL your responses must be output after `<reactAgentSegmentHeader>send_response_to_user</reactAgentSegmentHeader>` BLOCK
"""


def get_typeset_handler(api, browser):
    def escape_html(text: str) -> str:
        """Escapes HTML special characters in the text."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    async def handle_shut_up(x: dict, group_id: int) -> tuple[str, str]:
        user = x["user_id"]
        time = x["minutes"]
        time = 10 if time > 10 else (time if time > 0 else 1)
        await api.set_group_ban(group_id, user, time * 60)
        return f" 已禁言[CQ:at,qq={user}]{time}分钟 "

    async def handle_tts(x: dict) -> str:
        text = x["text"]
        emotion = x.get("emotion", "")
        log_func("INFO", entity_name, f"Text to speech: {text}")
        result = await aibackend_package["tts"].text_to_speech_cosyvoice(text, emotion)
        result = base64.b64encode(result).decode()
        return f"[CQ:record,file=base64://{result}]"

    async def handle_wolfram(x: dict, markdown: bool) -> str:
        cal = x["script"]
        result = await document_renderer_package[
            "renderer"
        ].wolfram_alpha.wolfram_alpha_compute(cal, image_only=True)

        if markdown:
            return (
                "\n"
                + await document_renderer_package[
                    "renderer"
                ].wolfram_alpha.format_to_HTML(result)
                + "\n"
            )
        formatted = (
            "\n"
            + await document_renderer_package["renderer"].wolfram_alpha.format_to_CQ(
                result
            )
            + "\n"
        )
        return formatted if formatted is not None else "Failed to calculate"

    async def handle_markdown_render(x: dict) -> str:
        try:
            markdown_str = x["content"]
            result = await document_renderer_package["renderer"].MarkdownRenderer(
                browser
            )(markdown_str)
            if result is None:
                return "Failed to render Markdown"
            return (
                f"[CQ:image,file=base64://{base64.b64encode(result).decode()},id=40000]"
            )
        except Exception as e:
            log_func("ERROR", entity_name, f"Failed to render markdown: {e}")
            return markdown_str

    async def handle_graphic_art(x: dict) -> str:
        is_vertical = x.get("vertical", False)
        style = x.get("style", "anime")
        prompt = x["prompt"]
        size = (
            aibackend_package["aipaint"].ImageSize.TALL
            if is_vertical
            else aibackend_package["aipaint"].ImageSize.WIDE
        )
        style = (
            aibackend_package["aipaint"].ImageStyle.ANIME
            if style == "anime"
            else aibackend_package["aipaint"].ImageStyle.PHOTO
        )
        try:
            result = await aibackend_package["aipaint"].generate_image(
                prompt, size, style, aibackend_package["aipaint"].APILevel.PRO
            )
            return f"[CQ:image,file=base64://{base64.b64encode(result).decode()}]"
        except Exception as e:
            log_func("ERROR", entity_name, f"Failed to generate image: {e}")
            return f"Failed to generate image: {e}"

    async def handle_image_from_url(tag: BeautifulSoup) -> str:
        url = tag.get("src")
        if not url or not url.startswith(("http://", "https://")):
            return "[图片错误: 无效的URL]"

        log_func("INFO", entity_name, f"Processing image URL: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                # 1. 先用 HEAD 请求检查 URL 和内容类型，避免下载大文件
                async with session.head(url, timeout=10) as response:
                    if response.status != 200:
                        return f"[图片错误: URL无法访问，状态码 {response.status}]"

                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        return f"[图片错误: URL指向的不是一个图片文件 ({content_type})]"

                # 2. 检查通过后，再用 GET 请求下载图片内容
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        encoded_data = base64.b64encode(image_data).decode("utf-8")
                        return f"[CQ:image,file=base64://{encoded_data}]"
                    else:
                        return f"[图片错误: 下载失败，状态码 {response.status}]"

        except asyncio.TimeoutError:
            return "[图片错误: 访问URL超时]"
        except Exception as e:
            log_func("ERROR", entity_name, f"Error processing image URL {url}: {e}")
            return f"[图片错误: 处理时发生未知异常]"

    async def handle_at_user(tag: BeautifulSoup) -> str:
        qq_number = tag.get("qq")
        try:
            qq_number = int(qq_number)
            return f"[CQ:at,qq={qq_number}]"
        except (ValueError, TypeError):
            return f"@{qq_number}"

    return {
        "DocumentRender": handle_markdown_render,
        "shut_up": handle_shut_up,
        "text_to_speech": handle_tts,
        "display_wolframalpha": handle_wolfram,
        "graphic_art_in_English": handle_graphic_art,
        "image_from_url": handle_image_from_url,
        "at_user": handle_at_user,
    }


def convert_html_to_readable_text(html_content: str) -> str:
    """
    Converts HTML content to a human-readable, Markdown-like plain text.
    - Handles headers, lists, links, and tables gracefully.
    - The output is fully copy-paste friendly.
    """
    if not html_content:
        return ""

    # 创建一个 html2text 转换器实例
    h = html2text.HTML2Text()

    # --- 可选的配置，让输出更好看 ---
    # 不换行处理链接，而是将链接显示在括号里，如：[Google](http.google.com)
    h.body_width = 0
    # 标题使用 #, ## 样式
    h.style_headers_with_dashes = False
    # Google风格的表格
    h.google_doc = True
    # 链接使用Markdown格式
    h.use_automatic_links = True

    try:
        # 执行转换
        text = h.handle(html_content)
        return text
    except Exception as e:
        log_func("ERROR", entity_name, f"html2text conversion failed: {e}")
        # 如果转换失败，回退到简单的 get_text
        soup = BeautifulSoup(html_content, "lxml")
        return soup.get_text(separator="", strip=True)


async def handle_agent_output(
    html_output: str,
    api: Any,  # Pass the onebot api instance
    browser: Any,  # Pass the browser instance
    group_id: int,  # Pass the group_id for context
) -> List[str]:
    """
    Parses the agent's HTML output, executes special action tags,
    and returns a list of strings ready to be sent to the message API.
    If there are top-level <hr> tags, the content will be split into multiple messages.
    """
    if not BeautifulSoup:
        log_func("ERROR", "Chat", "BeautifulSoup is not installed, returning raw HTML.")
        return html_output

    soup = BeautifulSoup(html_output, "lxml")

    # Get the legacy handler functions, which we will reuse
    legacy_handlers = get_typeset_handler(api, browser)

    # Process each custom tag type

    # <tts>
    for tag in soup.find_all("tts"):
        result_cq = await legacy_handlers["text_to_speech"](
            {"text": tag.get_text(strip=True), "emotion": tag.get("emotion", "")}
        )
        tag.replace_with(result_cq)  # Replace the tag with the [CQ:record] code

    # <tti>
    for tag in soup.find_all("tti"):
        result_cq = await legacy_handlers["graphic_art_in_English"](
            {
                "prompt": tag.get_text(strip=True),
                "style": tag.get("style", "anime"),
                "vertical": tag.get("orientation") == "tall",
            }
        )
        tag.replace_with(result_cq)  # Replace with [CQ:image]

    # <wolfram>
    for tag in soup.find_all("wolfram"):
        result_cq = await legacy_handlers["display_wolframalpha"](
            {"script": tag.get_text(strip=True)}, markdown=False
        )  # Get CQ code, not HTML
        tag.replace_with(result_cq)

    # <document-render>
    for tag in soup.find_all("document-render"):
        # We need to be careful here to avoid infinite recursion if document-render itself contains action tags
        # The content should be plain markdown, but we preserve the raw HTML structure inside the tag
        raw_content = tag.decode_contents()  # 使用decode_contents()获取原始HTML内容
        result_cq = await legacy_handlers["DocumentRender"](
            {"content": raw_content},  # 传递原始HTML内容
        )
        tag.replace_with(result_cq)

    # <image src="...">
    for tag in soup.find_all("image"):
        result_cq = await legacy_handlers["image_from_url"](tag)
        tag.replace_with(result_cq)

    # <at qq="...">
    for tag in soup.find_all("at"):
        result_cq = await legacy_handlers["at_user"](tag)
        tag.replace_with(result_cq)

    remaining_html = str(soup)

    # 检查是否有顶层hr标签需要分割消息
    soup_for_split = BeautifulSoup(remaining_html, "lxml")

    # 查找所有顶层的hr标签（直接在body下的，不嵌套在其他标签内）
    top_level_hrs = []
    body = soup_for_split.find("body")
    if body:
        for child in body.children:
            if hasattr(child, "name") and child.name == "hr":
                top_level_hrs.append(child)

    # 如果没有顶层hr标签，返回单个消息的列表（向后兼容）
    if not top_level_hrs:
        final_text = convert_html_to_readable_text(remaining_html)
        return [final_text]

    # 如果有顶层hr标签，按这些标签分割内容
    message_parts = []
    current_content = []

    if body:
        for child in body.children:
            if hasattr(child, "name") and child.name == "hr":
                # 遇到hr标签，处理当前积累的内容
                if current_content:
                    # 直接拼接HTML字符串
                    part_html = "".join(str(item) for item in current_content)
                    part_text = convert_html_to_readable_text(part_html)
                    if part_text.strip():  # 只添加非空内容
                        message_parts.append(part_text)
                    current_content = []
            else:
                # 不是hr标签，添加到当前内容
                current_content.append(child)

        # 处理最后一部分内容
        if current_content:
            part_html = "".join(str(item) for item in current_content)
            part_text = convert_html_to_readable_text(part_html)
            if part_text.strip():
                message_parts.append(part_text)

    # 如果分割后没有有效内容，返回原始内容
    if not message_parts:
        final_text = convert_html_to_readable_text(remaining_html)
        return [final_text]

    return message_parts


class Plugin:
    context_manager = None
    lock = Lock()
    rate_limiter = plugin_context.RateLimiter(300, 400)

    # All static methods (create, help, description, destroy, etc.) remain UNCHANGED.
    @staticmethod
    def create():
        Plugin.context_manager = ContextManager()
        try:
            Plugin.context_manager.read_from_temporary_file()
            log_func(
                "INFO",
                entity_name,
                "Context loaded from temporary file successfully!",
            )
        except Exception as e:
            log_func(
                "WARN",
                entity_name,
                "Failed to load context from temporary file, creating new context...",
            )
            Plugin.context_manager = ContextManager()

        log_func(
            "INFO",
            entity_name,
            r"""

AI Chat Plugin is initialized!
""",
        )

    @staticmethod
    def help():
        return r"""
AI Chat Plugin
================
This plugin is used to chat with AI.

Commands:
- `#context --save_all`: Save all context to temporary file.
- `#context --load_all`: Load all context from temporary file.
- `#sudo --set_trigger trigger1 trigger2 ... `: Set trigger for AI.
- `#sudo --set_instruction "system instruction"`: Set instruction for AI. Empty to reset to default.
""".strip()

    @staticmethod
    def description():
        return r"""
AI Chat Plugin
================
This plugin is used to chat with AI.
Powered by ✨Gemini-Flash-2.5 via AutoGemini Agent
""".strip()

    @staticmethod
    def destroy():
        try:
            Plugin.context_manager.write_to_temporary_file()
            log_func(
                "INFO",
                entity_name,
                "Context saved to temporary file successfully!",
            )
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to save context to temporary file! {traceback.format_exc()}",
            )

    @staticmethod
    def before_reload():
        with Plugin.lock:
            log_func("INFO", entity_name, "Writing context to temporary file...")
            Plugin.context_manager.write_to_temporary_file()
            log_func(
                "INFO", entity_name, "Context written to temporary file successfully."
            )

    @staticmethod
    def after_reload():
        with Plugin.lock:
            log_func("INFO", entity_name, "Reading context from temporary file...")
            Plugin.context_manager = ContextManager()
            Plugin.context_manager.read_from_temporary_file()
            log_func(
                "INFO", entity_name, "Context read from temporary file successfully."
            )

    @staticmethod
    def _test_if_being_at(message, bot_qq):
        for x in message:
            if x["type"] == "at" and x["data"]["qq"] == str(bot_qq):
                return True
        return False

    @staticmethod
    async def process_sudo_command(message, group_context, message_sender_func):
        sender = message["sender"]
        command = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image(
            message["message"], message["self_id"]
        )

        command = command.strip()
        if not command.startswith(plugin_context.bot_entity.sudo_command_trigger):
            return
        if not sender["user_id"] in plugin_context.bot_entity.admins:
            await message_sender_func("Permission denied.")
            log_func(
                "ERROR",
                "Bot",
                "Permission denied for sudo command:",
                command,
                "because",
                sender["user_id"],
                "is not in the admin list.",
            )
            raise plugin_context.SkipFollow()
        command = command.replace(
            plugin_context.bot_entity.sudo_command_trigger, "", 1
        ).strip()
        log_func("INFO", "Bot", "Received sudo command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            if "set_trigger" in command_json:
                group_context["ai_params"]["trigger"] = command_json["set_trigger"]
                await message_sender_func("Set trigger successfully.")
                raise plugin_context.SkipFollow()
            if "set_instruction" in command_json:
                if command_json["set_instruction"] == []:
                    group_context["ai_params"][
                        "system_instruction"
                    ] = get_default_system_instruction()
                else:
                    group_context["ai_params"]["system_instruction"] = command_json[
                        "set_instruction"
                    ][0]
                await message_sender_func("Set instruction successfully.")
                raise plugin_context.SkipFollow()
        except plugin_context.SkipFollow:
            raise plugin_context.SkipFollow()
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)

    @staticmethod
    async def process_context_command(message, message_sender_func, context):
        command = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image(
            message["message"], message["self_id"]
        )

        command = command.strip()
        trigger = "#context "
        if not command.startswith(trigger):
            return

        command = command.replace(trigger, "", 1).strip()
        log_func("INFO", "Bot", "Received context command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            if "save_all" in command_json:
                Plugin.context_manager.write_to_temporary_file()
                await message_sender_func("Save context successfully.")
            if "load_all" in command_json:
                Plugin.context_manager.read_from_temporary_file()
                await message_sender_func("Load context successfully.")
            if "clear" in command_json:
                context["context"].clear()
                await message_sender_func("Clear context successfully.")
            if "withdraw" in command_json:
                context["context"].withdraw()
                await message_sender_func("Withdraw context successfully.")

        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)
        raise plugin_context.SkipFollow()

    # --- CORE LOGIC: on_group_message is completely refactored ---
    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)

        async def timeout_callback():
            await api.send_group_message(message["group_id"], "AI Chat Plugin Timeout!")

        @plugin_context.timeout(600, timeout_callback=timeout_callback)
        async def handler():
            group_id = message["group_id"]
            group_context = Plugin.context_manager.get_group_context(group_id)

            await Plugin.process_sudo_command(
                message, group_context, lambda x: api.send_group_message(group_id, x)
            )
            await Plugin.process_context_command(
                message, lambda x: api.send_group_message(group_id, x), group_context
            )

            # 使用优化的消息处理，避免冗余的图片转文本
            message_text_for_trigger, _ = await extract_media_from_message(
                message["message"]
            )

            def check_trigger(message):
                for trigger in group_context["ai_params"]["trigger"]:
                    if trigger in message:
                        return True
                return False

            @plugin_context.async_ratelimit(
                limiter=Plugin.rate_limiter,
                on_limit_exceeded=lambda wait_time: None,
                throw_on_limit=True,
            )
            async def limited_handler():
                pass

            if Plugin._test_if_being_at(
                message["message"], message["self_id"]
            ) or check_trigger(message_text_for_trigger):
                await limited_handler()

                log_func(
                    "INFO", entity_name, f"Triggered by message from group {group_id}."
                )
                message_id = await api.send_group_message(
                    group_id, "我正在思考如何回复你 (Agent模式)..."
                )

                # --- AGENT INTEGRATION BLOCK ---

                # 调试：检查原始消息内容
                log_func(
                    "DEBUG", entity_name, f"Original message data: {message['message']}"
                )

                # 0. 提取当前消息中的媒体文件（包含文本和图片）
                current_message_text, current_media_files = (
                    await extract_media_from_message(message["message"])
                )

                # 调试：检查提取的媒体文件
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Extracted message text: {current_message_text}",
                )
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Extracted media files count: {len(current_media_files) if current_media_files else 0}",
                )
                if current_media_files:
                    for i, media_info in enumerate(current_media_files):
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"Media file {i}: type={media_info.get('mime_type', 'unknown')}, data_length={len(media_info.get('data', ''))}",
                        )
                else:
                    log_func(
                        "WARN", entity_name, "No media files extracted from message"
                    )

                # 1. Build the full context using the NEW, powerful build_context method.
                full_context_list, real_request_for_history = (
                    await Plugin.context_manager.build_context(
                        api,
                        group_context["context"].get_message(),  # 核心对话
                        message["user_id"],
                        message["message_id"],
                        current_message_text,  # 使用提取的纯文本（不包含图片转文本）
                        group_context["stream_context"],  # 群聊历史
                        group_id,
                    )
                )

                # 2. The last message in the list is the current user's prompt. Separate it.
                current_user_message_dict = full_context_list.pop()
                current_user_prompt = current_user_message_dict.get("content", "")

                # 3. Convert the rest of the list into the agent's history format.
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Converting {len(full_context_list)} history items to ChatMessages",
                )
                for i, item in enumerate(full_context_list):
                    if "media_files" in item:
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"History item {i} has media_files: {len(item['media_files'])}",
                        )
                    else:
                        log_func(
                            "DEBUG", entity_name, f"History item {i} has no media_files"
                        )

                agent_history = convert_history_to_chat_messages(full_context_list)

                # 调试：检查历史记录中的媒体文件
                media_count_in_history = 0
                for i, chat_msg in enumerate(agent_history):
                    if chat_msg.media_files:
                        media_count_in_history += len(chat_msg.media_files)
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"History message {i}: {len(chat_msg.media_files)} media files",
                        )
                log_func(
                    "DEBUG",
                    entity_name,
                    f"Total media files in history: {media_count_in_history}",
                )

                # 4. Prepare the agent by creating its tools and API handler.
                agent_api_handler = await create_agent_api_handler(group_id, api)
                agent_tool_codes = get_agent_tool_codes()

                ai_api_key = get_api_key()
                if not ai_api_key:
                    await api.withdraw_message(message_id)
                    await api.send_group_message(
                        group_id, "错误：机器人未配置API Key。"
                    )
                    log_func(
                        "ERROR",
                        entity_name,
                        "Gemini API Key not found in bot_entity config.",
                    )
                    return

                addtitional_prompt = f"""# Since you are an AI agent in a group chat, you must carefully consider the `# Group Message History Context` before responding.
This context is crucial for understanding the conversation and providing relevant responses.

Your own QQ number is [CQ:at,qq={message['self_id']}]
"""

                # 5. Create a new agent processor for this specific request.
                processor = create_cot_processor(
                    api_key=ai_api_key,
                    default_api=agent_api_handler,
                    tool_codes=agent_tool_codes,
                    character_description=addtitional_prompt
                    + "\n"
                    + group_context["ai_params"]["system_instruction"],
                    respond_tags_description=CUSTOM_TAGS_PROMPT,
                    model="deepseek-chat",
                    temperature=1.0,
                    max_tokens=8192,
                    api_delay=5.0,
                    api_type=APIType.OPENAI,
                    base_url="https://api.deepseek.com",
                    presence_penalty=0.0,
                    enable_multimodal=False,
                )

                # 6. Load the conversation history into the agent.
                processor.load_history(agent_history)

                # 7. Define a simple callback for debugging the agent's internal steps.
                async def stream_callback(chunk: Any, msg_type: CallbackMsgType):
                    log_func("DEBUG", f"Agent-{msg_type.name}", str(chunk))
                async def raw_stream_callback(response):
                    log_func("DEBUG", f"Agent-RAW", str(response))

                # 8. 创建包含媒体文件的当前用户消息
                current_user_chat_message = ChatMessage(
                    role=MessageRole.USER, content=current_user_prompt
                )

                # 添加媒体文件到当前消息
                SUPPORTED_MEDIA_TYPES = {
                    "image/jpeg",
                    "image/jpg",
                    "image/png",
                    "image/webp",
                }

                for media_info in current_media_files:
                    try:
                        mime_type = media_info["mime_type"]

                        # 检查媒体类型是否被支持
                        if mime_type not in SUPPORTED_MEDIA_TYPES:
                            log_func(
                                "WARN",
                                entity_name,
                                f"Skipping unsupported media type in current message: {mime_type}",
                            )
                            continue

                        media_data = base64.b64decode(media_info["data"])
                        media_file = MediaFile(data=media_data, mime_type=mime_type)
                        current_user_chat_message.media_files.append(media_file)
                        log_func(
                            "INFO",
                            entity_name,
                            f"Added media file to message: {mime_type}, size: {len(media_data)} bytes",
                        )
                    except Exception as e:
                        log_func("WARN", entity_name, f"Failed to add media file: {e}")
                        log_func(
                            "DEBUG",
                            entity_name,
                            f"Media file error traceback: {traceback.format_exc()}",
                        )

                # 调试：验证媒体文件是否正确添加
                if current_user_chat_message.media_files:
                    log_func(
                        "INFO",
                        entity_name,
                        f"Total media files in message: {len(current_user_chat_message.media_files)}",
                    )
                    for i, mf in enumerate(current_user_chat_message.media_files):
                        log_func(
                            "INFO",
                            entity_name,
                            f"Media file {i}: {mf.mime_type}, data length: {len(mf.data) if mf.data else 0}",
                        )
                else:
                    log_func(
                        "WARN",
                        entity_name,
                        "No media files were successfully added to the message",
                    )

                # 9. Run the agent's processing loop with media support.
                try:
                    log_func(
                        "INFO",
                        entity_name,
                        "Starting agent processing with media support...",
                    )

                    # 仿照_process_with_toolcode_loop，直接添加包含媒体文件的消息到历史记录
                    processor.history.append(current_user_chat_message)

                    # 重置处理状态
                    processor.current_response = ""
                    processor.processing_complete = False

                    # 直接调用_process_with_toolcode_loop进行处理
                    final_response = await processor._process_with_toolcode_loop(
                        callback=stream_callback,
                        raw_response_callback=raw_stream_callback,
                        tool_code_timeout=90.0,
                        max_cycle_cost=5,
                    )

                    # 9. Process and send the final response.
                    await api.withdraw_message(message_id)

                    agent_output = parse_agent_output(final_response)
                    ai_output = "No response"
                    for item in agent_output:
                        if item.type == "send_response_to_user":
                            ai_output = item.content

                    parsed_outputs = await handle_agent_output(
                        ai_output,
                        api,
                        await plugin_context.bot_entity.browser.get_browser(),
                        group_id,
                    )

                    # 现在handle_agent_output返回消息列表，分别发送每条消息
                    for message_part in parsed_outputs:
                        message_part = message_part.strip()
                        if message_part:  # 只发送非空消息
                            await api.send_group_message_separate_audio(
                                group_id,
                                await message_codec_package[
                                    "codec"
                                ].decode_CQ_to_message(message_part),
                            )

                    # 10. Save the complete interaction to context manager.
                    current_time = time.time()

                    # 构造包含媒体文件的用户消息记录
                    user_message_record = {
                        "role": "user",
                        "content": real_request_for_history,
                        "timestamp": current_time,
                    }

                    # 如果有媒体文件，保存媒体信息（为了向前兼容）
                    if current_media_files:
                        user_message_record["media_files"] = current_media_files
                        log_func(
                            "INFO",
                            entity_name,
                            f"Saved {len(current_media_files)} media files to context",
                        )

                    group_context["context"].push_message(user_message_record)

                    group_context["context"].push_message(
                        {
                            "role": "assistant",
                            "content": final_response,
                            "timestamp": current_time
                            + 0.001,  # <--- ADDED (确保在用户消息之后)
                        }
                    )
                except Exception as e:
                    await api.withdraw_message(message_id)
                    error_msg = f"Agent在处理时发生错误: {e}"
                    log_func(
                        "ERROR", entity_name, f"{error_msg}\n{traceback.format_exc()}"
                    )
                    await api.send_group_message(group_id, error_msg)

                # --- END AGENT INTEGRATION BLOCK ---

            else:
                # 处理非触发消息，添加到流式上下文
                stream_message_text, stream_media_files = (
                    await extract_media_from_message(message["message"])
                )

                stream_message_record = {
                    "role": "user",
                    "name": message["sender"]["nickname"],
                    "user_id": message["user_id"],
                    "message_id": message["message_id"],
                    "content": stream_message_text,
                    "timestamp": time.time(),
                }

                # 如果有媒体文件，也保存到流式上下文中（虽然不会传递给AI，但保持完整性）
                if stream_media_files:
                    stream_message_record["media_files"] = stream_media_files

                group_context["stream_context"].push_message(stream_message_record)

        try:
            await handler()
        except plugin_context.SkipFollow:
            raise plugin_context.SkipFollow()
        except plugin_context.Skip:
            raise plugin_context.Skip()
        except plugin_context.RateLimitedError as e:
            await api.send_group_message(message["group_id"], str(e))
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle group message: {traceback.format_exc()}",
            )
            await api.send_group_message(
                message["group_id"], "AI聊天插件处理消息失败！\n" + str(e)
            )

    # on_poke remains unchanged. It cleverly reuses on_group_message.
    @staticmethod
    async def on_poke(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)
        group_id = message["group_id"]
        fake_message = {
            "message_id": message.get("message_id", "0"),
            "group_id": group_id,
            "user_id": message.get("user_id", "0"),
            "self_id": message.get("self_id", "0"),
            "sender": message.get(
                "sender",
                {"nickname": "unknown", "user_id": message.get("user_id", "0")},
            ),
            "message": [
                {"type": "text", "data": {"text": "[戳一戳]"}},
                {"type": "at", "data": {"qq": str(message.get("target_id", "0"))}},
            ],
        }
        try:
            await Plugin.on_group_message(ws, fake_message)
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle poke as group message: {traceback.format_exc()}",
            )
            await api.send_group_message(group_id, "处理戳一戳时出错！")
