import base64
from typing import Callable, Any

import asyncio
from xlang import XLang, Context, NoneType, String
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

document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
document_renderer = document_renderer_package.load_module(
    "renderer", hot_reload=True, log_func=log_func
)


entity_name = "Tools"

tools_help = r"""
快速工具
- mdr <markdown>: 渲染 markdown 为图片。
- typst <typst>: 渲染 typst 为图片。
- $ <xlang>: 执行 XLang 代码。
"""


class XLangContexts:
    def __init__(self):
        self.contexts = {}

    def get_context(self, group_id):
        if group_id not in self.contexts:
            self.contexts[group_id] = {
                "context": Context(),
                "stack": [],
                "interpreter": XLang(),
            }
            self.contexts[group_id]["context"].new_frame(
                stack=self.contexts[group_id]["stack"], enter_func=True
            )
            self.contexts[group_id]["interpreter"].create_builtins_for_context(
                self.contexts[group_id]["context"]
            )
            log_func(f"XLang context created for group {group_id}")
        return self.contexts[group_id]

    def remove_context(self, group_id):
        if group_id in self.contexts:
            del self.contexts[group_id]


class Plugin:

    xlang_contexts = XLangContexts()

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
                    ].MarkdownRenderer(plugin_context.bot_entity.browser)(markdown)
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

            typst_trigger = "typst "
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

            xlang_trigger = "$"
            if encoded_message.startswith(xlang_trigger):
                xlang = encoded_message[len(xlang_trigger):]
                if xlang.strip() == "clear()":
                    Plugin.xlang_contexts.remove_context(message["group_id"])
                    await api.send_group_message(
                        message["group_id"], "XLang context cleared!"
                    )
                    raise plugin_context.SkipFollow()
                try:

                    def execute():
                        context = Plugin.xlang_contexts.get_context(message["group_id"])

                        output_buffer = ""
                        error_buffer = ""
                        is_error = False

                        def print_func(args):
                            list_args = [arg.value for arg in args]
                            output_printer(*list_args)
                            return NoneType()

                        def input_func(args):
                            return String(input_reader())
                        
                        context["context"].get("print").func = print_func
                        context["context"].get("input").func = input_func

                        def output_printer(*args, sep=" ", end="\n"):
                            nonlocal output_buffer
                            output_buffer += sep.join(map(str, args)) + end

                        def input_reader(*args):
                            return ""

                        def error_printer(*args, sep=" ", end="\n"):
                            nonlocal error_buffer
                            error_buffer += sep.join(map(str, args)) + end
                            nonlocal is_error
                            is_error = True

                        result = NoneType()

                        try:
                            result = context["interpreter"].execute_with_context(
                                xlang,
                                context["context"],
                                context["stack"],
                                error_printer=error_printer,
                                output_printer=output_printer,
                                input_reader=input_reader,
                            )
                        except Exception as e:
                            error_printer(str(e))
                            is_error = True
                        finally:
                            output_printer(str(result))

                        return {
                            "output": output_buffer,
                            "error": error_buffer,
                            "is_error": is_error,
                        }

                    async def xlang_timeout_callback():
                        await api.send_group_message(
                            message["group_id"], "XLang 执行超时！"
                        )

                    @plugin_context.timeout(10, timeout_callback=xlang_timeout_callback)
                    async def run_xlang():
                        # 创建一个任务在线程池中执行 XLang 代码
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, execute)

                        if result["is_error"]:
                            await api.send_group_message(
                                message["group_id"],
                                f"执行出错:\n{result['error']}\n输出:\n{result['output']}",
                            )
                        else:
                            await api.send_group_message(
                                message["group_id"], f"执行结果:\n{result['output']}"
                            )

                    await run_xlang()

                except Exception as e:
                    await api.send_group_message(
                        message["group_id"], f"Failed to run xlang:\n{str(e)}"
                    )
                    raise plugin_context.SkipFollow()
                raise plugin_context.SkipFollow()

        await handler()
