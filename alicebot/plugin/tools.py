import base64
from typing import Callable, Any
log_func: Callable[[Any], None]
plugin_context: Any # 插件上下文，由插件管理器传入

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)

document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
document_renderer = document_renderer_package.load_module(
    "renderer", hot_reload=True, log_func=log_func
)


entity_name = "Tools"

tools_help = r'''
快速工具
- mdr <markdown>: 渲染 markdown 为图片。
- typst <typst>: 渲染 typst 为图片。
'''


class Plugin:
    @staticmethod
    def help():
        return tools_help.strip()

    @staticmethod
    def description():
        return r'''Just a tools plugin for daily use.'''

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
            await api.send_group_message(message["group_id"], "Timeout!")
        @plugin_context.timeout(60, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            encoded_message = encoded_message.strip()

            mdr_trigger = "mdr "
            if encoded_message.startswith(mdr_trigger):
                markdown = encoded_message[len(mdr_trigger):]
                result = await document_renderer_package["renderer"].MarkdownRenderer(
                    plugin_context.bot_entity.browser
                )(markdown)
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
                typst = encoded_message[len(typst_trigger):]
                result = await document_renderer_package[
                    "renderer"
                ].typst_render.render_async(typst)
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
        await handler()
