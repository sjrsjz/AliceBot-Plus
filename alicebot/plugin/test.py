from typing import Callable, Any
log_func: Callable[[Any], None]
timeout: Any # timeout装饰器
bot_entity: Any # bot实体
Skip: Any # Skip异常
SkipFollow: Any # SkipFollow异常
echo_pool: Any # echo_pool
onebot_package_path: str # onebot包路径
message_codec_package_path: str # message_codec包路径

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(message_codec_package_path, log_func=log_func)
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
        api = onebot_package['api'].OneBotAPI(echo_pool)
        async def timeout_callback():
            pass
        @timeout(5, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            if "test" in encoded_message:
                await api.send_group_message(ws, message["group_id"], message=encoded_message)
            
        await handler()

