from typing import Callable, Any
log_func: Callable[[Any], None]
plugin_context: Any # 插件上下文，由插件管理器传入

from loader import moduleloader
onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)


entity_name = "Help"

bot_help = r'''
AliceBot+ Framework Help
- #help: Show this help message.
- #sudo <fjson/json>: execute sudo command.
    + --plugin: switch to plugin mode.
    + --enable: enable plugin.
    + --disable: disable plugin.
    > Example: #sudo --plugin --enable test
- #plugin
    + --ls: list all plugins.
    + --help <plugin_name>: show plugin help message.
    + --description <plugin_name>: show plugin description.
    > Example: #plugin --help test
'''


class Plugin:
    @staticmethod
    def help():
        return bot_help.strip()

    @staticmethod
    def description():
        return r'''Just a help plugin.'''

    @staticmethod
    def create():
        log_func('INFO', 'Help', r'''

Welcome to the AliceBot+ framework!
         
To use TUI, you can use the following control keys:
- Ctrl + C: Exit the program.
- W: Scroll up.
- S: Scroll down.
- PageUp: Scroll up a page.
- PageDown: Scroll down a page.
- Space: Scroll down to the bottom.
''')


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
        api = onebot_package['api'].OneBotAPI(plugin_context.echo_pool)
        async def timeout_callback():
            pass
        @plugin_context.timeout(5, timeout_callback=timeout_callback)
        async def handler():
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"])
            if encoded_message.strip() == "#help":
                await api.send_group_message(ws, message["group_id"], message=bot_help.strip())
            
        await handler()

