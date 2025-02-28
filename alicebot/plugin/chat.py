import pathlib
import fJson as fjson
import time
import traceback
import base64
import os
import asyncio
from threading import Lock
from typing import Callable, Any

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
aibackend_package.load_module(
    "gemini", hot_reload=True, log_func=log_func
)  # AI Backend
aibackend_package.load_module("tts", hot_reload=True, log_func=log_func)  # AI Backend
aibackend_package.load_module(
    "aipaint", hot_reload=True, log_func=log_func
)  # AI Backend


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

entity_name = "Chat"


context_temp_path = pathlib.Path(__file__).parent / "context_temp"
context_temp_path.mkdir(parents=True, exist_ok=True)
context_temp_file = context_temp_path / "context_temp.fjson"

profile_path = pathlib.Path(__file__).parent / "profiles"
profile_path.mkdir(parents=True, exist_ok=True)

# 导入该文件目录下的util/online_py_executor.py
from plugin.util import online_py_executor


def get_default_system_instruction():
    return example_prompt_package["Alice"].character


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
                    max_length=50,
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
            f.write(
                fjson.encode(
                    {
                        "group_context": group_context,
                        "private_context": private_context,
                    },
                    multi_line=True,
                    indent=4,
                )
            )

    def read_from_temporary_file(self):
        with open(context_temp_file, "r", encoding="utf-8") as f:
            context = fjson.decode(f.read())
            self.group_context = {}
            self.private_context = {}
            self.group_context = {
                str(k): {
                    "context": message_codec_package["context"].ContextManager(
                        context=v["context"]
                    ),
                    "stream_context": message_codec_package[
                        "context"
                    ].StreamContextManager(
                        context=v["stream_context"][0],
                        max_length=v["stream_context"][1],
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in context["group_context"].items()
            }
            self.private_context = {
                str(k): {
                    "context": message_codec_package["context"].ContextManager(
                        context=v["context"]
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in context["private_context"].items()
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
        context,
        user_id,
        user_message_id,
        user_request,
        stream_context,
        group_id=None,
    ):
        _context = context.copy()

        async def build_header(
            user_id, user_message_id, user_sex, user_name, current=False
        ):
            return (
                ("# Current User(Talking to the assistant):" if current else "# User:")
                + f'`[CQ:at,qq={user_id}]`\n## msgid:`[CQ:reply,id={user_message_id}]`\n## Time:{time.asctime()}\n## User Sex:{user_sex}\n## User Name:"{user_name}"\n## User Request:\n'
            )

        profile = await self.get_profile(user_id)

        async def get_autosaves_file_informations():
            # 获取文件信息（文件名，大小，修改时间，创建时间）
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
        autosave_str = "# My files saved in the past:\n"
        autosave_str += "filename | modify time\n --- | --- \n"
        for autosave in autosaves:
            autosave_str += f"{autosave['filename']} | {autosave['modify_time']}\n"

        _context.insert(
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
                formatted_member_list = "```group member list\ncard | nickname | gender | qq\n --- | --- | --- | ---\n"
                for member in group_member_list:
                    formatted_member_list += f"{member['card']} | {member['nickname']} | {member['sex']} | {member['user_id']}\n"
                formatted_member_list += "```"
            elif len(group_member_list) <= 500:
                # 只保留nickname和qq，如果card存在则用card替换nickname
                formatted_member_list = (
                    "```group member list\nnickname | qq\n --- | ---\n"
                )
                for member in group_member_list:
                    nickname = (
                        member["card"] if member["card"] != None else member["nickname"]
                    )
                    formatted_member_list += f"{nickname} | {member['user_id']}\n"
                formatted_member_list += "```"
            else:
                formatted_member_list = (
                    "```group member list\nmember count exceeds 500\n```"
                )

            _context.insert(
                0,
                {
                    "role": "user",
                    "content": f"# Group Member List:\n{formatted_member_list}",
                },
            )

        if stream_context:
            stream_context_str = ""
            for item in stream_context.get_message():
                stream_context_str += f"""# [{item['role']}: {item['name']}]([CQ:at,qq={item['user_id']}], {item['time']}, [CQ:reply,id={item['message_id']}]):\n{item['content']}\n\n"""
            _context.insert(
                0,
                {
                    "role": "user",
                    "content": f"# Additional Group Message History Context (Multi-Users):\n{stream_context_str}",
                },
            )

        user_info = await api.get_stranger_info(user_id)

        if user_info != None:
            if "sex" in user_info:
                user_sex = user_info["sex"]
            else:
                user_sex = "unknown"
            if "nickname" in user_info:
                user_name = user_info["nickname"]
            else:
                user_name = "unknown"
            chat_request = (
                await build_header(user_id, user_message_id, user_sex, user_name)
                + user_request
            )
            _context.append(
                {
                    "role": "user",
                    "content": "# Current User Profile:"
                    + str(profile)
                    + "\n"
                    + await build_header(
                        user_id, user_message_id, user_sex, user_name, True
                    )
                    + user_request,
                }
            )
        else:
            chat_request = (
                await build_header(user_id, user_message_id, "unknown", "unknown")
                + user_request
            )
            _context.append(
                {
                    "role": "user",
                    "content": "# Current User Profile:"
                    + str(profile)
                    + "\n"
                    + await build_header(
                        user_id, user_message_id, "unknown", "unknown", True
                    )
                    + user_request,
                }
            )

        return _context, chat_request


def get_typeset_handler(api, browser, template):
    async def handle_shut_up(x: dict, group_id: int, **kwargs) -> tuple[str, str]:
        user = x["user_id"]
        time = x["minutes"]
        time = 10 if time > 10 else (time if time > 0 else 1)
        await api.set_group_ban(group_id, user, time * 60)
        return f" 已禁言[CQ:at,qq={user}]{time}分钟 "

    async def handle_write_file(x: dict, **kwargs) -> str:
        content = x["content"]
        file_name = x["filename"]

        with open(profile_path / file_name, "w", encoding="utf-8") as f:
            f.write(content)
        return f" [{file_name}]已保存 "

    async def handle_tts(x: dict, **kwargs) -> str:
        text = x["text"]
        emotion = x.get("emotion", "")
        log_func("INFO", entity_name, f"Text to speech: {text}")
        result = await aibackend_package["tts"].text_to_speech_cosyvoice(text, emotion)
        result = base64.b64encode(result).decode()
        return f"[CQ:record,file=base64://{result}]"

    async def handle_wolfram(x: dict, markdown: bool, **kwargs) -> str:
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

    async def handle_markdown_render(
        x: dict, _FUNCTION_HANDLERS=None, markdown=False, **kwargs
    ) -> str:
        try:
            markdown_str = x["content"]
            markdown_str = await template.process_chatbot_typeset(
                markdown_str,
                FUNCTION_HANDLERS=_FUNCTION_HANDLERS,
                markdown=True,
                _FUNCTION_HANDLERS=_FUNCTION_HANDLERS,
                **kwargs,
            )
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

    async def handle_graphic_art(x: dict, **kwargs) -> str:
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
        result = await aibackend_package["aipaint"].generate_image(
            prompt, size, style, aibackend_package["aipaint"].APILevel.FREE
        )
        return f"[CQ:image,file=base64://{base64.b64encode(result).decode()}]"

    return {
        "DocumentRender": handle_markdown_render,
        "shut_up": handle_shut_up,
        "write_to_file": handle_write_file,
        "text_to_speech": handle_tts,
        "display_wolframalpha": handle_wolfram,
        "graphic_art_in_English": handle_graphic_art,
    }


def get_available_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_on_web",
                "description": "Perform a web search only if you do not know the information (excluding mathematical queries, use 'calculate' instead). Use this function sparingly, **no more than 3 times** because it is **expensive**.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The content to search on the web if you do not know the answer.",
                        },
                        "search_engine": {
                            "type": "string",
                            "description": "The search engine to use, e.g., Google.",
                        },
                    },
                    "required": ["query", "search_engine"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_webpage_from_url",
                "description": "open url in browser and retrieve the content of the specified webpage in Markdown format directly",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "webpage": {
                            "type": "string",
                            "description": "The URL which you want to open in the browser",
                        }
                    },
                    "required": ["webpage"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_mathematical_expression_with_wolfram_alpha",
                "description": "Compute the mathematical expression using Wolfram Alpha. Useful for complex calculations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "The mathematical expression to compute, e.g., 'integrate x^2'.",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "python_execute",
                "description": "Execute Python code in sandboxed environment. Not able to access the network and local files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The Python code to execute. Cannot access the network and local files. Never, Never use this tool to save files, you should use the `tool_code`: `write_to_file` instead",
                        }
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "require_render_format",
                "description": "Determine whether to render Markdown or HTML or image in the conversation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "render_format": {
                            "type": "string",
                            "enum": [
                                "Markdown",
                                "HTML",
                                "Image",
                                "LaTeX",
                                "Write to file",
                                "Typst document",
                            ],
                            "description": "Determine whether to render Markdown or HTML or image or write something to local files in the conversation",
                        }
                    },
                    "required": ["render_format"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skip_tool_call",
                "description": "Skip using tools in the conversation, only use this function if you think other tools like search_on_web are not needed",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skip": {
                            "type": "boolean",
                            "description": "Whether to skip using tools in the conversation",
                        }
                    },
                    "required": ["skip"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_from_file",
                "description": "Read something from files what you have written before",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filenames": {
                            "type": "string",
                            "description": "The name of the file to read from, separate multiple files with |",
                        }
                    },
                    "required": ["filenames"],
                },
            },
        },
    ]


async def handle_tools(tool_name, args):
    log_func("INFO", entity_name, f"Tool: {tool_name} with args: {args}")
    if tool_name == "search_on_web":
        return await document_renderer_package["renderer"].web_search(
            plugin_context.bot_entity.browser, args["query"], 20, "Bing"
        )
    elif tool_name == "get_webpage_from_url":
        return await document_renderer_package["renderer"].get_webpage(
            plugin_context.bot_entity.browser,
            args["webpage"],
            only_text=True,
            max_token=4096,
        )
    elif tool_name == "python_execute":
        return await online_py_executor.execute_python_code(args["code"])
    elif tool_name == "compute_mathematical_expression_with_wolfram_alpha":
        return await document_renderer_package[
            "renderer"
        ].wolfram_alpha.wolfram_alpha_compute_without_image(args["expression"])
    elif tool_name == "require_render_format":
        if args["render_format"] == "Markdown":
            return "[System]Markdown is required in the conversation, use `tool_code` to render the Markdown content"
        elif args["render_format"] == "HTML":
            return "[System]HTML is required in the conversation, use `tool_code` to warp the HTML content to render the HTML content"
        elif args["render_format"] == "Image":
            return "[System]Image is required in the conversation"
        elif args["render_format"] == "LaTeX":
            return "[System]LaTeX is required in the conversation, use $...$ to warp the mathematical expression"
        elif args["render_format"] == "Write to file":
            return "[System]Write to file is required in the conversation, use `tool_code` to write content to file"
        elif args["render_format"] == "Typst document":
            return "[System]Typst document is required in the conversation, use `tool_code` to warp the Typst document content. Remember the Typst document is only available in the `tool_code` block"
        return "[System]" + args["render_format"] + " is required in the conversation"
    elif tool_name == "generate_plan_of_what_to_do":
        return "[System][Plan What to Do Next] " + args["plan"]
    elif tool_name == "skip_tool_call":
        return "[System]Skipped tool call"
    elif tool_name == "read_from_file":
        files = args["filenames"].split("|")
        result_dict = {}
        for file in files:
            try:
                with open(profile_path / file, "r", encoding="utf-8") as f:
                    result_dict[file] = f.read()
            except Exception as e:
                result_dict[file] = f"[System]Failed to read file '{file}': {e}"
        return result_dict
    else:
        return "Unknown or Invalid Tool: " + tool_name + " with args: " + str(args)


class Plugin:
    context_manager = None
    lock = Lock()
    rate_limiter = plugin_context.RateLimiter(300, 400)

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
Powered by ✨Gemini-Flash-2.0
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

    @staticmethod
    def after_reload():
        with Plugin.lock:
            log_func("INFO", entity_name, "Reading context from temporary file...")
            Plugin.context_manager = ContextManager()
            Plugin.context_manager.read_from_temporary_file()

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
        ].encode_message_to_CQ_without_At_self_and_Image_tag(
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
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)
        raise plugin_context.SkipFollow()

    @staticmethod
    async def process_context_command(message, message_sender_func, context):
        command = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image_tag(
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

            message_str = await message_codec_package[
                "codec"
            ].encode_message_to_CQ_without_At_self_and_Image_tag(
                message["message"], message["self_id"]
            )

            def check_trigger(message):
                for trigger in group_context["ai_params"]["trigger"]:
                    if trigger in message:
                        return True
                return False

            async def on_limit_exceeded(wait_time):
                pass

            @plugin_context.async_ratelimit(
                limiter=Plugin.rate_limiter,
                on_limit_exceeded=on_limit_exceeded,
                throw_on_limit=True,
            )
            async def limited_handler():
                pass

            if Plugin._test_if_being_at(
                message["message"], message["self_id"]
            ) or check_trigger(message_str):
                await limited_handler()  # 检查是否超过限制

                log_func(
                    "INFO",
                    entity_name,
                    f"Received a message from group {group_id}, being at.\n{message_str}",
                )
                message_id = await api.send_group_message(
                    group_id, "我正在思考如何回复你..."
                )
                message_str = await message_codec_package[
                    "codec"
                ].encode_message_to_CQ_without_At_self_and_Image(
                    message["message"], message["self_id"]
                )

                ai_context, real_request = await Plugin.context_manager.build_context(
                    api,
                    group_context["context"].get_message(),
                    message["user_id"],
                    message["message_id"],
                    message_str,
                    group_context["stream_context"],
                    group_id,
                )

                template = prompt_package["template"]

                ai_response = await aibackend_package["gemini"].chat_gemini_with_tools(
                    ai_context,
                    get_available_tools(),
                    handle_tools,
                    template.COT_template(
                        example_typeset_package["QQBot"].typesets,
                        group_context["ai_params"]["system_instruction"],
                    ),
                )

                await api.withdraw_message(message_id)

                if ai_response != None:

                    group_context["context"].push_message(
                        {
                            "role": "user",
                            "content": real_request,
                        }
                    )
                    group_context["context"].push_message(
                        {
                            "role": "assistant",
                            "content": ai_response,
                        }
                    )

                    log_func(
                        "INFO",
                        entity_name,
                        f"Gemini AI Chat Plugin Response: {ai_response}",
                    )

                    extracted_response = template.extract_response(ai_response)

                    splited_response = template.split_response(extracted_response)

                    for response in splited_response:
                        try:
                            FUNCTION_HANDLERS = get_typeset_handler(
                                api, plugin_context.bot_entity.browser, template
                            )
                            processed_response = await template.process_chatbot_typeset(
                                response,
                                FUNCTION_HANDLERS,
                                markdown=False,
                                group_id=group_id,
                                _FUNCTION_HANDLERS=FUNCTION_HANDLERS,
                            )
                        except Exception as e:
                            log_func(
                                "ERROR",
                                entity_name,
                                f"Failed to process chatbot typeset: {traceback.format_exc()}",
                            )
                            processed_response = response

                        await api.send_group_message_separate_audio(
                            group_id,
                            await message_codec_package["codec"].decode_CQ_to_message(
                                processed_response
                            ),
                        )
                        await asyncio.sleep(5)
            else:

                group_context["stream_context"].push_message(
                    {
                        "role": "user",
                        "name": message["sender"]["nickname"],
                        "user_id": message["user_id"],
                        "time": time.asctime(),
                        "message_id": message["message_id"],
                        "content": message_str,
                    }
                )

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
                message["group_id"],
                "AI Chat Plugin Failed to Handle Message!\n" + str(e),
            )

    @staticmethod
    async def on_poke(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)
        group_id = message["group_id"]

        # 创建一个伪造的消息结构，模拟一条群消息
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
                # 添加一个at机器人自己的部分，确保触发回复
                {"type": "at", "data": {"qq": str(message.get("target_id", "0"))}},
            ],
        }

        # 调用群消息处理函数处理这个伪造的消息
        try:
            await Plugin.on_group_message(ws, fake_message)
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle poke as group message: {traceback.format_exc()}",
            )
            await api.send_group_message(group_id, "处理戳一戳时出错！")
