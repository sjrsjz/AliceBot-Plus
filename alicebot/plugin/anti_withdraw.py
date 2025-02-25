from typing import Callable, Any
import os
import time

log_func: Callable[[Any], None]
plugin_context: Any  # 插件上下文，由插件管理器传入

from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(
    plugin_context.onebot_package_path, log_func=log_func
)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)


file = None
plugin_path = os.path.dirname(os.path.abspath(__file__))


class Plugin:
    @staticmethod
    def help():
        return """-反撤回插件-
使用方法:
无"""

    @staticmethod
    def description():
        return "反撤回插件"

    @staticmethod
    def create():
        log_func("INFO", "AntiWithdraw", "反撤回插件已加载")
        if not os.path.exists(plugin_path + "/anti_withdraw_data"):
            os.mkdir(plugin_path + "/anti_withdraw_data")
        global file
        time_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        file = open(
            f"{plugin_path}/anti_withdraw_data/{time_str}_{time.time()}.txt",
            "w",
            encoding="utf-8",
        )

    @staticmethod
    def destroy():
        global file
        if file:
            file.close()

    @staticmethod
    def before_reload():
        global file
        if file:
            file.close()
    @staticmethod
    def after_reload():
        if not os.path.exists(plugin_path + "/anti_withdraw_data"):
            os.mkdir(plugin_path + "/anti_withdraw_data")
        global file
        time_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        file = open(
            f"{plugin_path}/anti_withdraw_data/{time_str}_{time.time()}.txt",
            "w",
            encoding="utf-8",
        )

    @staticmethod
    async def on_group_message(ws, message):
        async def timeout_callback():
            pass

        @plugin_context.timeout(5, timeout_callback=timeout_callback)
        async def handler():
            try:
                await Plugin.anti_withdraw(
                    message["group_id"], message["message"], message["user_id"]
                )
            except Exception as e:
                log_func("ERROR", "AntiWithdraw", f"Error: {e}")

        await handler()

    @staticmethod
    async def anti_withdraw(group_id, cmd, user_id=None):
        global file
        file.write(f"[{time.asctime()}][Group:{group_id}][User:{user_id}]{cmd}\n")
        file.flush()
