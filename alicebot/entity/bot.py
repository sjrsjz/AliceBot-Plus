import asyncio
import websockets
import sys
import os
import pathlib
import fJson as fjson
import enum

from typing import Callable, Any
log_func: Callable[[Any], None]


project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent.parent / "onebot"), log_func=log_func)
onebot_api_module = onebot_package.load_module("api", hot_reload=True, log_func=log_func)

message_codec_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "message"), log_func=log_func)
message_codec = message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)

from util.timeout import timeout

plugin_dir = pathlib.Path(__file__).parent.parent / "plugin"
plugin_package = moduleloader.ModuleLoader(str(plugin_dir), log_func=log_func) # Import the plugin package

if not plugin_dir.exists():
    plugin_dir.mkdir()
# 枚举所有插件
plugin_names = [x for x in os.listdir(str(plugin_dir)) if '.py' in x]


class PluginStatus(enum.Enum):
    ACTIVE = 1
    INACTIVE = 0

class PluginPermission(enum.Enum):
    ADMIN = 1
    USER = 0


meta_path = plugin_dir / "meta.json"

@fjson.DataClass
class PluginMeta:
    def __init__(self, meta = {}):
        self.meta = meta
    def activate_plugin(self, plugin_name, meta_path = meta_path):
        self.meta[plugin_name]['active'] = PluginStatus.ACTIVE
        self.save(meta_path=meta_path)

    def deactivate_plugin(self, plugin_name, meta_path = meta_path):
        self.meta[plugin_name]['active'] = PluginStatus.INACTIVE
        self.save(meta_path=meta_path)

    def set_plugin_permission(self, plugin_name, permission, meta_path = meta_path):
        self.meta[plugin_name]['permission'] = permission
        self.save(meta_path=meta_path)

    def get_plugin_permission(self, plugin_name, meta_path = meta_path):
        return self.meta.get(plugin_name, {}).get('permission', PluginPermission.USER)    
    def get_plugin_status(self, plugin_name, meta_path = meta_path):
        return self.meta.get(plugin_name, {}).get('active', PluginStatus.INACTIVE)
    
    def save(self, meta_path = meta_path):
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(self.json(indent=4, multi_line=True))

    def load(self, meta_path = meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            self.load_json(f.read())

plugin_meta = PluginMeta()
if not meta_path.exists():
    plugin_meta.save()
else:
    plugin_meta.load()

log_func("[🟨|Bot]Plugin meta:", plugin_meta.json())
class Bot:
    def __init__(self, echo_pool):
        self.bot_qq = None
        self.echo_pool = echo_pool
    def _test_if_being_at(self, message):
        for x in message:
            if x["type"] == "at" and x["data"]["qq"] == str(self.bot_qq):
                return True
        return False


    async def receive_group_message(self, ws: websockets.WebSocketClientProtocol, message):
        global log_func
        if not self._test_if_being_at(message["message"]):
            return
        log_func("[🟨|Bot]Received group message: ", message)
        
        api = onebot_package['api'].OneBotAPI(self.echo_pool)
        
        async def timeout_callback():
            group_id = message["group_id"]
            await api.send_group_message(ws, group_id, "Timeout!")
            raise asyncio.TimeoutError("Timeout!")
        @timeout(5, timeout_callback)
        async def reply():
            await asyncio.sleep(10) # Simulate a long-time operation
            group_id = message["group_id"]
            message = await message_codec_package['codec'].encode_message_to_CQ_without_At_self_and_Image(message["message"], self.bot_qq)
            await api.send_group_message(ws, group_id, await message_codec_package['codec'].decode_CQ_to_message(message))
        await reply()

    async def create(self, ws: websockets.WebSocketClientProtocol):
        pass

    async def destroy(self, ws: websockets.WebSocketClientProtocol):
        pass