import pathlib
import fJson as fjson
import time
import traceback
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


prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path, log_func=log_func
)
template = prompt_package.load_module("template", log_func=log_func)

example_prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path / "example" / "character", log_func=log_func
)
example_prompt_package.load_module("Alice", hot_reload=True, log_func=log_func)

entity_name = "Chat"


context_temp_path = pathlib.Path(__file__).parent / "context_temp"
context_temp_path.mkdir(parents=True, exist_ok=True)
context_temp_file = context_temp_path / "context_temp.fjson"

profile_path = pathlib.Path(__file__).parent / "profiles"

def get_default_system_instruction():
    return example_prompt_package["Alice"].character

class ContextManager:
    def __init__(self):
        self.group_context = {}
        self.private_context = {}

    def get_group_context(self, group_id):
        if str(group_id) not in self.group_context:
            self.group_context[str(group_id)] = {
                "context": message_codec_package["context"].ContextManager(
                    context = []
                ),
                "stream_context": message_codec_package[
                    "context"
                ].StreamContextManager(
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
                    {"group_context": group_context, "private_context": private_context}, multi_line=True, indent=4
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

    async def get_profile(self, group_id, user_id):
        group_profile_file = profile_path / f"{group_id}.json"
        if not group_profile_file.exists():
            return None
        try:
            with open(group_profile_file, "r", encoding="utf-8") as f:
                profiles = fjson.decode(f.read())
                if profiles == None:
                    return None
                if str(user_id) in profiles:
                    return profiles[str(user_id)]
                return None
        except Exception as e:
            log_func(
                "WARN",
                entity_name,
                f"Failed to get profile: {e}",
            )
            return None

    async def build_context(
        self,
        ws,
        api,
        context,
        user_id,
        user_message_id,
        user_request,
        stream_context,
        group_id=None,
    ):
        _context = context.copy()

        async def build_header(user_id, user_message_id, user_sex, user_name, current = False):
            return "# Current User(Talking to the assistant):" if current else "# User:" + f'`[CQ:at,qq={user_id}]`\n## msgid:`[CQ:reply,id={user_message_id}]`\n## Time:{time.asctime()}\n## User Sex:{user_sex}\n## User Name:"{user_name}"\n## User Request:\n'

        profile = await self.get_profile(group_id, user_id)

        if group_id:
            try:
                group_member_list = await api.get_member_list(ws, group_id)
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

        user_info = await api.get_stranger_info(ws, user_id)

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
                    + await build_header(user_id, user_message_id, user_sex, user_name, True)
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
                    + await build_header(user_id, user_message_id, "unknown", "unknown", True)
                    + user_request,
                }
            )

        return _context, chat_request


class Plugin:
    context_manager = None
    lock = Lock()

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
    async def process_command(message, group_context, message_sender_func):
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
            raise plugin_context.SkipFollow
        command = command.replace(plugin_context.bot_entity.sudo_command_trigger, "", 1).strip()
        log_func("INFO", "Bot", "Received sudo command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            # 检查是否包含 --plugin 参数
            if "set_trigger" in command_json:
                group_context["ai_params"]["trigger"] = command_json["set_trigger"]
                await message_sender_func("Set trigger successfully.")
            if "set_instruction" in command_json:
                group_context["ai_params"]["system_instruction"] = command_json["set_instruction"]
                await message_sender_func("Set instruction successfully.")
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)
        raise plugin_context.SkipFollow

    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package["api"].OneBotAPI(plugin_context.echo_pool)

        async def timeout_callback():
            await api.send_group_message(
                ws, message["group_id"], "AI Chat Plugin Timeout!"
            )

        @plugin_context.timeout(600, timeout_callback=timeout_callback)
        async def handler():
            group_id = message["group_id"]
            group_context = Plugin.context_manager.get_group_context(group_id)

            await Plugin.process_command(
                message, group_context, lambda x: api.send_group_message(ws, group_id, x)
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

            if Plugin._test_if_being_at(message["message"], message["self_id"]) or check_trigger(message_str):
                log_func(
                    "INFO",
                    entity_name,
                    f"Received a message from group {group_id}, being at.",
                )
                message_id = await api.send_group_message(
                    ws, group_id, "我正在思考如何回复你..."
                )
                message_str = await message_codec_package[
                    "codec"
                ].encode_message_to_CQ_without_At_self_and_Image(
                    message["message"], message["self_id"]
                )

                ai_context, real_request = await Plugin.context_manager.build_context(
                    ws,
                    api,
                    group_context["context"].get_message(),
                    message["user_id"],
                    message["message_id"],
                    message_str,
                    group_context["stream_context"],
                    group_id,
                )

                ai_response = await aibackend_package["gemini"].chat_gemini(
                    ai_context, group_context["ai_params"]["system_instruction"]
                )

                await api.withdraw_message(ws, message_id)

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

                    extracted_response = template.extract_response(ai_response)
                    log_func(
                        "INFO",
                        entity_name,
                        f"Gemini AI Chat Plugin Response: {ai_response}",
                    )
                    await api.send_group_message(ws, group_id, extracted_response)
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
        except plugin_context.SkipFollow: raise plugin_context.SkipFollow
        except plugin_context.Skip: raise plugin_context.Skip
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle group message: {traceback.format_exc()}",
            )
            await api.send_group_message(
                ws,
                message["group_id"],
                "AI Chat Plugin Failed to Handle Message!\n" + str(e),
            )
