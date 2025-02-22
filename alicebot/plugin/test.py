from typing import Callable, Any
log_func: Callable[[Any], None]
plugin_context: Any # 插件上下文，由插件管理器传入

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)


log_func(r'''
This is a test plugin for alicebot.
''')

class Plugin:
    @staticmethod
    async def create():
        log_func("[Test]Plugin created.")

    @staticmethod
    async def destroy():
        log_func("[Test]Plugin destroyed.")

    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package['api'].OneBotAPI(plugin_context.echo_pool)
        async def timeout_callback():
            pass
        @plugin_context.timeout(5, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            if "test" in encoded_message:
                await api.send_group_message(ws, message["group_id"], message=encoded_message)
            
        await handler()

