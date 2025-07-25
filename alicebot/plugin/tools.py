import base64
from typing import Callable, Any
import asyncio
import time
import pathlib

# onion 绑定
from onion import (
    eval as onion_eval,
    eval_or_throw as onion_eval_or_throw,
    PyOnionObject,
    wrap_py_function as onion_wrap_py_function,
    wrap_py_coroutine as onion_wrap_py_coroutine,
    OnionRuntimeError,
)


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
- $ <onion>: 执行 Onion 代码。
"""

# Onion 上下文管理
class OnionContexts:
    def __init__(self):
        self.contexts = {}

    def get_context(self, group_id):
        if group_id not in self.contexts:
            py_context = {}

            def onion_set(self_object, arguments):
                if len(arguments) != 1:
                    raise OnionRuntimeError("set() requires exactly one argument")
                if not arguments[0].is_named():
                    raise OnionRuntimeError("set() argument must be a named object")
                k = arguments[0].key()
                v = arguments[0].value()
                py_context[k.as_string()] = v

            def onion_get(self_object, arguments):
                # 返回 dict 形式
                return PyOnionObject(
                    [PyOnionObject.named(k, v) for k, v in py_context.items()]
                )

            def onion_clear(self_object, arguments):
                py_context.clear()

            wrapped_set = onion_wrap_py_function(
                PyOnionObject.tuple([]), "<python>::set", onion_set, None, None
            )
            wrapped_get = onion_wrap_py_function(
                PyOnionObject.tuple([]), "<python>::get", onion_get, None, None
            )
            wrapped_clear = onion_wrap_py_function(
                PyOnionObject.tuple([]), "<python>::clear", onion_clear, None, None
            )

            self.contexts[group_id] = {
                "py_context": py_context,
                "wrapped_set": wrapped_set,
                "wrapped_get": wrapped_get,
                "wrapped_clear": wrapped_clear,
            }
            log_func("INFO", f"Onion context created for group {group_id}")
        return self.contexts[group_id]

    def remove_context(self, group_id):
        if group_id in self.contexts:
            context = self.contexts[group_id]
            del context["wrapped_set"]
            del context["wrapped_get"]
            del context["wrapped_clear"]
            del context["py_context"]
            del self.contexts[group_id]


class Plugin:
    onion_contexts = OnionContexts()

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

            onion_trigger = "$"
            if encoded_message.startswith(onion_trigger):
                onion_code = encoded_message[len(onion_trigger) :]
                if onion_code.strip() == "clear()":
                    Plugin.onion_contexts.remove_context(message["group_id"])
                    await api.send_group_message(
                        message["group_id"], "Onion context cleared!"
                    )
                    raise plugin_context.SkipFollow()
                try:
                    @plugin_context.timeout(10, timeout_callback=timeout_callback)
                    async def run_onion():
                        context = Plugin.onion_contexts.get_context(message["group_id"])
                        # 传递 context 变量
                        onion_context = [
                            PyOnionObject.named("let", context["wrapped_set"]),
                            PyOnionObject.named("context", context["wrapped_get"]),
                            PyOnionObject.named("clear", context["wrapped_clear"]),
                        ]
                        try:
                            result = await onion_eval_or_throw(
                                f"""
Modules := mut ();
@required stdlib;
@required let;
@required context;

{onion_code}""",
                                work_dir=str(pathlib.Path(__file__).parent / "modules"),
                                context=onion_context,
                            )
                            output = str(result)
                            if output.strip() == "" or output.strip() == "None":
                                await api.send_group_message(
                                    message["group_id"], "Success!"
                                )
                            else:
                                await api.send_group_message(
                                    message["group_id"], output.strip()
                                )
                        except OnionRuntimeError as e:
                            await api.send_group_message(
                                message["group_id"], f"Onion error: {e}"
                            )
                        except Exception as e:
                            await api.send_group_message(
                                message["group_id"], f"Failed to run onion: {e}"
                            )

                    await run_onion()
                except Exception as e:
                    await api.send_group_message(
                        message["group_id"], f"Failed to run onion:\n{str(e)}"
                    )
                    raise plugin_context.SkipFollow()
                raise plugin_context.SkipFollow()

        await handler()
