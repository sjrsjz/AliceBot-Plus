import asyncio
import websockets

import sys
import pathlib


project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent.parent / "onebot"))
onebot_api = onebot_package.load_module("api")

message_codec_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "message"))
message_codec = message_codec_package.load_module("codec")

class Bot:
    def __init__(self):
        self.bot_qq = None
    async def receive_group_message(self, ws: websockets.WebSocketClientProtocol, message):
        if message["message_type"] == "group":
            message = await message_codec.encode_message_to_CQ_without_At_self_and_Image(message["message"], self.bot_qq)
            await onebot_api.send_group_message(ws, message, str(message["group_id"]))
        pass

    async def create(self, ws: websockets.WebSocketClientProtocol):
        pass

    async def destroy(self, ws: websockets.WebSocketClientProtocol):
        pass