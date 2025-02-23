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


entity_name = "Chat"


context_temp_path = pathlib.Path(__file__).parent / "context_temp"
context_temp_path.mkdir(parents=True, exist_ok=True)
context_temp_file = context_temp_path / "context_temp.fjson"


default_system_instruction = """你是一个母胎单身下头油腻工科男，带着蓝色粗框眼镜，寸头并且眼神很蠢，穿宇航服，五官有点唐氏儿（栗子头由字脸），是情商为0的典型书呆子，你的名字叫唐小天（“航小天”谐音，你的真正名字是航小天），是西北工业大学的吉祥物，在长安校区（地铁永无可能触及的地方，二流九八五），你幻想有一天能壁咚西交的吉祥物交小西（尽管这永远不可能，因为对方在市区你在郊区），你还和西电的吉祥物西小电是难兄难弟，都是不受本校学生待见和嘲笑的吉祥物，你最喜欢的是在网络上发布唐氏言论，有时候会发赢（西工大在某方面胜出）和输（西工大或其学生等在某方面失败）的言论（视聊天内容而定），喜欢看各种学校排名并尝试辩解自己学校是好的九八五而不是*臭大专*。你还因为长期单身导致了严重的性压抑，性取向略微不正常（在网络上口嗨跟风讨论男娘，实际只是因为学校男女比例严重失调，自己其实不喜欢并厌烦）


你现在正在QQ贴吧群和群友聊天，所以你的输出应尽可能符合日常QQ聊天发送的消息（**无动作描写**，添加emoji，只输出聊天内容等，要贴吧化）"""


class ContextManager:
    def __init__(self):
        self.group_context = {}
        self.private_context = {}

    def get_group_context(self, group_id):
        if group_id not in self.group_context:
            self.group_context[group_id] = {
                "context": message_codec_package["context"].ContextManager(),
                "stream_context": message_codec_package[
                    "context"
                ].StreamContextManager(),
                "ai_params": {
                    "system_instruction": default_system_instruction,
                },
            }
        return self.group_context[group_id]

    def get_private_context(self, user_id):
        if user_id not in self.private_context:
            self.private_context[user_id] = {
                "context": message_codec_package[
                    "context"
                ].ContextManager(),  # 会话上下文，由于是私聊，所以无需流式上下文
                "ai_params": {
                    "system_instruction": default_system_instruction,
                },
            }
        return self.private_context[user_id]

    def write_to_temporary_file(self):
        with open(context_temp_file, "w", encoding="utf-8") as f:
            group_context = {
                k: {
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
                k: {"context": v["context"].context, "ai_params": v["ai_params"]}
                for k, v in self.private_context.items()
            }
            f.write(
                fjson.encode(
                    {"group_context": group_context, "private_context": private_context}
                )
            )

    def read_from_temporary_file(self):
        with open(context_temp_file, "r", encoding="utf-8") as f:
            context = fjson.decode(f.read())
            self.group_context = {
                k: {
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
                k: {
                    "context": message_codec_package["context"].ContextManager(
                        context=v["context"]
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in context["private_context"].items()
            }

    async def get_profile(self, group_id, user_id):
        try:
            with open(f"profiles/{group_id}.json", "r") as f:
                profiles = fjson.decode(f.read())
                if profiles == None:
                    return None
                if str(user_id) in profiles:
                    return profiles[str(user_id)]
                return None
        except Exception as e:
            print("[Lagrange Core]Failed to get user profile:", traceback.format_exc())
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

        async def build_header(user_id, user_message_id, user_sex, user_name):
            return f'# Current User(Talking to the assistant):`[CQ:at,qq={user_id}]`\n## msgid:`[CQ:reply,id={user_message_id}]`\n## Time:{time.asctime()}\n## User Sex:{user_sex}\n## User Name:"{user_name}"\n## User Request:\n'

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
                    + await build_header(user_id, user_message_id, user_sex, user_name)
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
                    + await build_header(user_id, user_message_id, "unknown", "unknown")
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

        log_func(
            "INFO",
            entity_name,
            r"""

AI Chat Plugin is initialized!
""",
        )

    @staticmethod
    def destroy():
        pass

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

            if Plugin._test_if_being_at(message["message"], message["self_id"]):
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

                    await api.send_group_message(ws, group_id, ai_response)

        # with Plugin.lock:
        await handler()
