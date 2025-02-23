import asyncio
import websockets
import sys
import os
import pathlib
import fJson as fjson

from typing import Callable, Any

log_func: Callable[[Any], None]

project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

onebot_package_path = pathlib.Path(__file__).parent.parent / "onebot"
aibackend_package_path = pathlib.Path(__file__).parent.parent / "aibackend"
message_codec_package_path = pathlib.Path(__file__).parent / "message"

onebot_package = moduleloader.ModuleLoader(str(onebot_package_path), log_func=log_func)
onebot_api_module = onebot_package.load_module(
    "api", hot_reload=True, log_func=log_func
)

message_codec_package = moduleloader.ModuleLoader(
    str(message_codec_package_path), log_func=log_func
)
message_codec = message_codec_package.load_module(
    "codec", hot_reload=True, log_func=log_func
)

from util.timeout import timeout


class Bot:

    class PluginStatus:
        ACTIVE = 1
        INACTIVE = 0

    class PluginPermission:
        ADMIN = 1
        USER = 0

    class Skip(Exception):  # 跳过当前插件
        pass

    class SkipFollow(Exception):  # 跳过当前插件的后续插件
        pass

    def __init__(self, echo_pool):
        self.bot_qq = None
        self.echo_pool = echo_pool
        self.plugin_meta = None
        self.plugin_dir = pathlib.Path(__file__).parent.parent / "plugin"
        self.plugin_package = None
        self.admins = []
        self.bot_config_path = pathlib.Path(__file__).parent.parent / "config"
        self.sudo_command_trigger = "#sudo"

    async def sudo_command(
        self,
        ws: websockets.WebSocketClientProtocol,
        command: str,
        message_sender_func,
        sender,
    ):
        command = command.strip()
        if not command.startswith(self.sudo_command_trigger):
            return
        if not sender["user_id"] in self.admins:
            await message_sender_func("Permission denied.")
            log_func(
                "ERROR",
                "Bot",
                "Permission denied for sudo command:",
                command,
                "because",
                sender["user_id"],
                "is not in the admin list.",
            )
            return
        command = command.replace(self.sudo_command_trigger, "", 1).strip()
        log_func("INFO", "Bot", "Received sudo command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            # 检查是否包含 --plugin 参数
            if "plugin" in command_json:
                log_text = ""
                if "enable" in command_json:
                    for plugin_name in command_json["enable"]:
                        log_func("INFO", "Bot", "Enable plugin:", plugin_name)
                        self.plugin_meta.activate_plugin(plugin_name)
                        log_text += f"Enabled plugin: {plugin_name}\n"
                if "disable" in command_json:
                    for plugin_name in command_json["disable"]:
                        log_func("INFO", "Bot", "Disable plugin:", plugin_name)
                        self.plugin_meta.deactivate_plugin(plugin_name)
                        log_text += f"Disabled plugin: {plugin_name}\n"
                await message_sender_func(log_text.strip())
                return

            await message_sender_func("Unknown command.")
            raise Exception("#sudo command is invalid: " + command)
        except Exception as e:
            log_func("ERROR", "Bot", "Error in sudo command:", e)
            await message_sender_func("Error in sudo command.")
            raise e

    async def receive_group_message(
        self, ws: websockets.WebSocketClientProtocol, message
    ):
        # 遍历所有插件
        for plugin_name, plugin in self.plugin_package.get_all_modules().items():
            if (
                self.plugin_meta.get_plugin_status(plugin_name)
                == Bot.PluginStatus.INACTIVE
            ):
                continue
            if (
                self.plugin_meta.get_plugin_permission(plugin_name)
                == Bot.PluginPermission.ADMIN
            ):
                if not message["sender"]["user_id"] in self.admins:
                    continue
            try:
                await plugin.Plugin.on_group_message(ws, message)
            except Bot.Skip:
                continue
            except Bot.SkipFollow:
                return  # 跳过后续插件以及默认回复
            except Exception as e:
                log_func("ERROR", "Bot", "Error in plugin", plugin_name, ":", e)

        api = onebot_package["api"].OneBotAPI(self.echo_pool)

        message_str = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image_tag(
            message["message"], self.bot_qq
        )
        await self.sudo_command(
            ws,
            message_str,
            lambda x: api.send_group_message(ws, message["group_id"], x),
            message["sender"],
        )

    async def create(self, ws: websockets.WebSocketClientProtocol):
        log_func("INFO", "Bot", "Creating bot entity...")
        self.plugin_package = moduleloader.ModuleLoader(
            str(self.plugin_dir), log_func=log_func
        )  # Import the plugin package

        if not self.plugin_dir.exists():
            self.plugin_dir.mkdir()
        # 枚举所有插件
        plugin_names = [x for x in os.listdir(str(self.plugin_dir)) if ".py" in x]

        meta_path = self.plugin_dir / "meta.json"

        @fjson.DataClass
        class PluginMeta:
            def __init__(self, meta={}):
                self.meta = meta.copy()
                pass

            def activate_plugin(self, plugin_name, meta_path=meta_path):
                self.meta[plugin_name]["active"] = Bot.PluginStatus.ACTIVE
                self.save(meta_path=meta_path)

            def deactivate_plugin(self, plugin_name, meta_path=meta_path):
                self.meta[plugin_name]["active"] = Bot.PluginStatus.INACTIVE
                self.save(meta_path=meta_path)

            def set_plugin_permission(
                self, plugin_name, permission, meta_path=meta_path
            ):
                self.meta[plugin_name]["permission"] = permission
                self.save(meta_path=meta_path)

            def get_plugin_permission(self, plugin_name, meta_path=meta_path):
                return self.meta.get(plugin_name, {}).get(
                    "permission", Bot.PluginPermission.USER
                )

            def get_plugin_status(self, plugin_name, meta_path=meta_path):
                return self.meta.get(plugin_name, {}).get(
                    "active", Bot.PluginStatus.INACTIVE
                )

            def save(self, meta_path=meta_path):
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(self.json(indent=4, multi_line=True))

            def load(self, meta_path=meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    loaded = self.load_json(f.read())
                    self.meta = loaded.meta

        self.plugin_meta = PluginMeta()
        if not meta_path.exists():
            self.plugin_meta.save()
        else:
            try:
                self.plugin_meta.load()
            except Exception as e:
                log_func("ERROR", "Plugin", "Failed to load plugin meta:", e)
                log_func("INFO", "Plugin", "Creating a new plugin meta file...")
                self.plugin_meta = PluginMeta()
                self.plugin_meta.save()

        log_func("DEBUG", "Plugin", "Plugin meta:", self.plugin_meta.json())

        for plugin_name in plugin_names:
            # 移除文件后缀
            plugin_name = plugin_name.split(".")[0]
            if plugin_name not in self.plugin_meta.meta:
                self.plugin_meta.meta[plugin_name] = {
                    "active": Bot.PluginStatus.INACTIVE,
                    "permission": Bot.PluginPermission.USER,
                }
        self.plugin_meta.save()

        # 装载所有插件
        for plugin_name in plugin_names:
            # 移除文件后缀
            plugin_name = plugin_name.split(".")[0]

            class PluginContext:
                def __init__(
                    self,
                    bot_entity,
                    plugin_meta,
                    Skip,
                    SkipFollow,
                    timeout,
                    echo_pool,
                    onebot_package_path=onebot_package_path,
                    message_codec_package_path=message_codec_package_path,
                    aibackend_package_path=aibackend_package_path,
                ):
                    self.bot_entity = bot_entity
                    self.plugin_meta = plugin_meta
                    self.Skip = Skip
                    self.SkipFollow = SkipFollow
                    self.timeout = timeout
                    self.echo_pool = echo_pool
                    self.onebot_package_path = onebot_package_path
                    self.message_codec_package_path = message_codec_package_path
                    self.aibackend_package_path = aibackend_package_path

            self.plugin_package.load_module(
                plugin_name,
                hot_reload=True,
                log_func=log_func,
                before_reload_callback=lambda plugin_name: self.plugin_package.get_module(
                    plugin_name
                ).Plugin.before_reload(),
                after_reload_callback=lambda plugin_name: self.plugin_package.get_module(
                    plugin_name
                ).Plugin.after_reload(),
                plugin_context=PluginContext(
                    self,
                    self.plugin_meta,
                    self.Skip,
                    self.SkipFollow,
                    timeout,
                    self.echo_pool,
                    onebot_package_path,
                    message_codec_package_path,
                    aibackend_package_path,
                ),
            )

        for plugin_name, plugin in self.plugin_package.get_all_modules().items():
            try:
                log_func("INFO", "Plugin", "Initializing plugin:", plugin_name)
                plugin.Plugin.create()
                log_func("INFO", "Plugin", "Plugin", plugin_name, "initialized.")
            except Exception as e:
                log_func(
                    "ERROR", "Plugin", "Initialize plugin", plugin_name, "failed:", e
                )

        @fjson.DataClass
        class BotConfig:
            def __init__(self):
                self.admins = []

            def save(self, path: str):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.json(indent=4, multi_line=True))

            @classmethod
            def load(cls, path: str):
                if not os.path.exists(path):
                    return cls()
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = fjson.decode(f.read())
                        config = cls()
                        if data:
                            config.admins = data.get("admins", [])
                        return config
                except Exception as e:
                    log_func("ERROR", "Config", f"Failed to load config: {e}")
                    return cls()

        self.bot_config_path = pathlib.Path(__file__).parent.parent / "config"
        if not self.bot_config_path.exists():
            self.bot_config_path.mkdir()
        self.bot_config_path = self.bot_config_path / "bot_config.json"
        if not self.bot_config_path.exists():
            with open(self.bot_config_path, "w", encoding="utf-8") as f:
                f.write(BotConfig().json(indent=4, multi_line=True))
        self.bot_config = BotConfig.load(self.bot_config_path)
        self.admins = self.bot_config.admins

        log_func("INFO", "Bot", "Bot entity created.")

    async def destroy(self, ws: websockets.WebSocketClientProtocol):
        log_func("INFO", "Bot", "Destroying bot entity...")
        for plugin_name, plugin in self.plugin_package.get_all_modules().items():
            try:
                log_func("INFO", "Plugin", "Destroying plugin:", plugin_name)
                plugin.Plugin.destroy()
                log_func("INFO", "Plugin", "Plugin", plugin_name, "destroyed")
            except Exception as e:
                log_func("ERROR", "Plugin", "Destroy plugin", plugin_name, "failed:", e)
        self.plugin_package = None
        self.plugin_meta.save()
        self.plugin_meta = None
        log_func("INFO", "Bot", "Bot entity destroyed.")
