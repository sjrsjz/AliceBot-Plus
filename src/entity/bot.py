import asyncio
import websockets

import sys
import pathlib


project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent.parent / "onebot"))
onebot_api_module = onebot_package.load_module("api", hot_reload=True)

message_codec_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "message"))
message_codec = message_codec_package.load_module("codec")

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
        if not self._test_if_being_at(message["message"]):
            return

        api = onebot_package.get_module('api').OneBotAPI(self.echo_pool)

        group_id = message["group_id"]
        message = await message_codec.encode_message_to_CQ_without_At_self_and_Image(message["message"], self.bot_qq)
        await api.send_group_message(ws, group_id, await message_codec.decode_CQ_to_message(message))

    async def create(self, ws: websockets.WebSocketClientProtocol):
        pass

    async def destroy(self, ws: websockets.WebSocketClientProtocol):
        pass