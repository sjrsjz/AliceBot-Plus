import base64
from typing import Callable, Any
import asyncio
import os
import re
from mutica_py import MuticaType, MuticaGC, MuticaEngine, MuticaError


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

document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
document_renderer = document_renderer_package.load_module(
    "renderer", hot_reload=True, log_func=log_func
)

aibackend_package = moduleloader.ModuleLoader(
    plugin_context.aibackend_package_path, log_func=log_func
)
aibackend_package.load_module("aipaint", hot_reload=True, log_func=log_func)
aibackend_package.load_module("apikey", hot_reload=True, log_func=log_func)


entity_name = "Tools"

tools_help = r"""
快速工具
- mdr <markdown>: 渲染 markdown 为图片。
- /typst <typst>: 渲染 typst 为图片。
- $ <mutica>: 执行 Mutica 代码。
- test-gen-image-size <style> <size> <prompt>: 测试图片生成（支持 nano-banana-2）。
"""


# Mutica 上下文管理
class MuticaContexts:
    def __init__(self):
        self.contexts = {}
        self.gc = MuticaGC()

    def get_context(self, group_id):
        if group_id not in self.contexts:
            engine = MuticaEngine()
            self.contexts[group_id] = {
                "engine": engine,
                "gc": self.gc,
            }
            log_func("INFO", f"Mutica context created for group {group_id}")
        return self.contexts[group_id]

    def remove_context(self, group_id):
        if group_id in self.contexts:
            del self.contexts[group_id]


class Plugin:
    mutica_contexts = MuticaContexts()

    @staticmethod
    def help():
        return tools_help.strip()

    @staticmethod
    def description():
        return r"""Just a tools plugin for daily use."""

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
            await api.send_group_message(message["group_id"], "Timeout!")

        @plugin_context.timeout(60, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package["codec"].encode_message_to_CQ(
                message["message"]
            )
            encoded_message = encoded_message.strip()

            mdr_trigger = "mdr "
            if encoded_message.startswith(mdr_trigger):
                markdown = encoded_message[len(mdr_trigger) :]
                try:
                    result = await document_renderer_package[
                        "renderer"
                    ].MarkdownRenderer(
                        await plugin_context.bot_entity.browser.get_browser()
                    )(
                        markdown
                    )
                except Exception as e:
                    await api.send_group_message(
                        message["group_id"], f"Failed to render markdown:\n{str(e)}"
                    )
                    raise plugin_context.SkipFollow()
                await api.send_group_message(
                    message["group_id"],
                    message={
                        "type": "image",
                        "data": {
                            "file": f"base64://{base64.b64encode(result).decode()}"
                        },
                    },
                )
                raise plugin_context.SkipFollow()

            typst_trigger = "/typst "
            if encoded_message.startswith(typst_trigger):
                typst = encoded_message[len(typst_trigger) :]
                try:
                    result = await document_renderer_package[
                        "renderer"
                    ].typst_render.render_async(typst)
                except Exception as e:
                    await api.send_group_message(
                        message["group_id"], f"Failed to render typst:\n{str(e)}"
                    )
                    raise plugin_context.SkipFollow()
                if isinstance(result, list):
                    for item in result:
                        await api.send_group_message(
                            message["group_id"],
                            message={
                                "type": "image",
                                "data": {
                                    "file": f"base64://{base64.b64encode(item).decode()}"
                                },
                            },
                        )
                else:
                    await api.send_group_message(
                        message["group_id"],
                        message={
                            "type": "image",
                            "data": {
                                "file": f"base64://{base64.b64encode(result).decode()}"
                            },
                        },
                    )
                raise plugin_context.SkipFollow()

            mutica_trigger = "$"
            if encoded_message.startswith(mutica_trigger):
                mutica_code = encoded_message[len(mutica_trigger) :]
                if mutica_code.strip() == "clear()":
                    Plugin.mutica_contexts.remove_context(message["group_id"])
                    await api.send_group_message(
                        message["group_id"], "Mutica context cleared!"
                    )
                    raise plugin_context.SkipFollow()
                try:

                    def strip_ansi_escape_sequences(text: str) -> str:
                        """移除字符串中的 ANSI 转义序列。"""
                        ansi_escape = re.compile(
                            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
                        )
                        return ansi_escape.sub("", text)

                    @plugin_context.timeout(10, timeout_callback=timeout_callback)
                    async def run_mutica():
                        nonlocal mutica_code
                        context = Plugin.mutica_contexts.get_context(
                            message["group_id"]
                        )
                        engine = context["engine"]
                        gc = context["gc"]

                        mutica_code = f"""
let result: any = {{
{mutica_code}
}};
match result
    | () => ()
    | _ => put! result
    | panic
"""
                        # chdir 到插件所在目录，确保文件操作正常
                        current_dir = os.getcwd()
                        os.chdir(__file__[: __file__.rfind(os.path.sep)])
                        errors = await engine.load(mutica_code, None, gc)
                        os.chdir(current_dir)
                        if errors:
                            error_messages = "\n".join(
                                [strip_ansi_escape_sequences(str(e)) for e in errors]
                            )
                            await api.send_group_message(
                                message["group_id"],
                                f"Mutica load error: {error_messages}",
                            )
                            return

                        output_buffer = ""

                        async def io_handler(
                            io: MuticaType, arg: MuticaType
                        ) -> MuticaType | None:
                            nonlocal output_buffer

                            io_py = io.as_py()
                            if not isinstance(io_py, dict):
                                return None
                            if not io_py.get("kind") == "Opcode":
                                return None
                            io_type = io_py.get("opcode")
                            if io_type[0] != "IO":
                                return None
                            io_name = io_type[1]
                            match io_name:
                                case "put":
                                    output_buffer += str(arg)
                                    return MuticaType.tuple([])
                                case "putln":
                                    output_buffer += str(arg) + "\n"
                                    return MuticaType.tuple([])
                                case _:
                                    return None

                        await engine.set_io_handler(io_handler)

                        while await engine.step(gc):
                            asyncio.sleep(0)

                        await api.send_group_message(
                            message["group_id"],
                            output_buffer,
                        )

                    await run_mutica()
                except Exception as e:
                    await api.send_group_message(
                        message["group_id"], f"Failed to run Mutica:\n{str(e)}"
                    )
                raise plugin_context.SkipFollow()

            # # 测试图片生成命令
            # test_gen_trigger = "test-gen-image-size "
            # if encoded_message.startswith(test_gen_trigger):
            #     test_command = encoded_message[len(test_gen_trigger):].strip()
                
            #     # 解析命令格式: <style> <size> <prompt>
            #     # 例如: anime tall a beautiful girl
            #     parts = test_command.split(maxsplit=2)
                
            #     if len(parts) < 3:
            #         await api.send_group_message(
            #             message["group_id"],
            #             "使用方法: test-gen-image-size <style> <size> <prompt>\n"
            #             "style: anime 或 photo\n"
            #             "size: tall, wide, 或 square\n"
            #             "prompt: 图片描述（英文）"
            #         )
            #         raise plugin_context.SkipFollow()
                
            #     style_str, size_str, prompt = parts[0], parts[1], parts[2]
                
            #     try:
            #         # 解析样式
            #         if style_str.lower() == "anime":
            #             style = aibackend_package["aipaint"].ImageStyle.ANIME
            #         elif style_str.lower() == "photo":
            #             style = aibackend_package["aipaint"].ImageStyle.PHOTO
            #         else:
            #             await api.send_group_message(
            #                 message["group_id"],
            #                 f"无效的风格: {style_str}，支持: anime, photo"
            #             )
            #             raise plugin_context.SkipFollow()
                    
            #         # 解析大小
            #         if size_str.lower() == "tall":
            #             size = aibackend_package["aipaint"].ImageSize.TALL
            #         elif size_str.lower() == "wide":
            #             size = aibackend_package["aipaint"].ImageSize.WIDE
            #         elif size_str.lower() == "square":
            #             size = aibackend_package["aipaint"].ImageSize.SQUARE
            #         else:
            #             await api.send_group_message(
            #                 message["group_id"],
            #                 f"无效的大小: {size_str}，支持: tall, wide, square"
            #             )
            #             raise plugin_context.SkipFollow()
                    
            #         await api.send_group_message(
            #             message["group_id"],
            #             f"正在生成图片...\n风格: {style_str}\n大小: {size_str}\n提示词: {prompt}"
            #         )
                    
            #         # 调用图片生成函数（使用 nano-banana-2）
            #         result = await aibackend_package["aipaint"].generate_image(
            #             prompt,
            #             size,
            #             style,
            #             aibackend_package["aipaint"].APILevel.PRO,
            #         )
                    
            #         await api.send_group_message(
            #             message["group_id"],
            #             message={
            #                 "type": "image",
            #                 "data": {
            #                     "file": f"base64://{base64.b64encode(result).decode()}"
            #                 },
            #             },
            #         )
            #         log_func("INFO", entity_name, f"成功生成图片: {style_str} {size_str} {prompt}")
                    
            #     except Exception as e:
            #         await api.send_group_message(
            #             message["group_id"],
            #             f"生成图片失败:\n{str(e)}"
            #         )
            #         log_func("ERROR", entity_name, f"生成图片错误: {e}")
                
            #     raise plugin_context.SkipFollow()

        await handler()
