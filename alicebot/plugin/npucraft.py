from typing import Callable, Any
log_func: Callable[[Any], None]
plugin_context: Any # 插件上下文，由插件管理器传入

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)


entity_name = "NPUHelp"

npu_help = r'''
NPUCraft 帮助
- 地图/卫星地图/ciallo: 显示地图URL
'''


class Plugin:
    @staticmethod
    def help():
        return npu_help.strip()

    @staticmethod
    def description():
        return r'''Just a NPU help plugin.'''

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
            pass
        @plugin_context.timeout(5, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            if encoded_message.strip() == "地图" or encoded_message.strip() == "卫星地图" or encoded_message.strip() == "ciallo":
                await api.send_group_message(
                    message["group_id"],
                    message="""【主服】Ciallo～(∠・ω< )⌒☆
平面 https://map.npucraft.com
【工业服】Ciallo～(∠・ω< )⌒☆
平面 https://map.npucraft.com/dynmap-industry
【资源服】Ciallo～(∠・ω< )⌒☆
平面 https://map.npucraft.com/dynmap-resource
全部地图请发送关键词 "Ciallo" """.strip(),
                )

        await handler()
