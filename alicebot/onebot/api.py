import asyncio
import json

from typing import Callable, Any

log_func: Callable[[Any], None]


class EchoPool:
    def __init__(self):
        self.echo_dict = {}
        self.echo_counter = 0
        self.close_event = asyncio.Event()


class OneBotAPI:
    def __init__(self, ws, echo_pool=None):
        self.ws = ws
        self.echo_pool = echo_pool

    async def _make_request(self, json_data):
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data["echo"] = self_echo
        await self.ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        return response
    async def get_stranger_info(self, user_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Getting stranger info:", user_id)
        json_data = {
            "action": "get_stranger_info",
            "params": {
                "user_id": user_id
            },
        }
        response = await self._make_request(json_data)
        if "data" in response and response["data"] is not None:
            log_func('INFO', 'OneBot', "Successfully got stranger info")
            return response["data"]
        log_func('ERROR', 'OneBot', "Failed to get stranger info")
        return None

    async def get_bot_group_list(self, async_mode=True):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Getting bot group list")
        json_data = {
            "action": "get_group_list",
            "params": {},
        }
        if not async_mode:
            self.echo_pool.echo_counter += 1
            self_echo = str(self.echo_pool.echo_counter)
            json_data["echo"] = self_echo
            await self.ws.send(json.dumps(json_data))
            return await self.ws.recv()
        response = await self._make_request(json_data)
        if "data" in response and response["data"] is not None:
            log_func('INFO', 'OneBot', "Successfully got bot group list")
            return response["data"]
        log_func('ERROR', 'OneBot', "Failed to get bot group list")
        return None

    async def get_member_list(self, group_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Getting member list of group:", group_id)
        json_data = {
            "action": "get_group_member_list",
            "params": {
                "group_id": group_id
            },
        }
        response = await self._make_request(json_data)
        if "data" in response and response["data"] is not None:
            log_func('INFO', 'OneBot', "Successfully got member list")
            return response["data"]
        log_func('ERROR', 'OneBot', "Failed to get member list")
        return None

    async def send_group_message(self, group_id, message, auto_escape=False):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Sending group message to group:", group_id)
        json_data = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": message,
                "auto_escape": auto_escape
            },
        }
        response = await self._make_request(json_data)
        if "status" in response:
            if response["status"] == "ok":
                log_func('INFO', 'OneBot', "Message sent successfully")
            else:
                log_func('ERROR', 'OneBot', "Failed to send group message")
        if response is None:
            return None
        if "data" in response and response["data"] is not None and "message_id" in response["data"]:
            log_func('INFO', 'OneBot', "Successfully sent group message")
            return response["data"]["message_id"]
        log_func('ERROR', 'OneBot', f"Failed to send group message, response: {response}")
        return None

    async def send_group_message_separate_audio(self, group_id, message, auto_escape=False):
        # 剥离音频消息单独发送
        other_message = []
        for i in message:
            if i["type"] == "record":
                if other_message:
                    await OneBotAPI.send_group_message(group_id, other_message, auto_escape)
                    other_message = []
                await OneBotAPI.send_group_message(group_id, [i], auto_escape)
            else:
                other_message.append(i)
        if other_message:
            await OneBotAPI.send_group_message(group_id, other_message, auto_escape)

    async def send_private_message(self, user_id, message, auto_escape=False):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Sending private message to user:", user_id)
        json_data = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": message,
                "auto_escape": auto_escape
            },
        }
        response = await self._make_request(json_data)
        if "status" in response:
            if response["status"] == "ok":
                log_func('INFO', 'OneBot', "Message sent successfully")
            else:
                log_func('INFO', 'OneBot', "Failed to send message")
        if response is None:
            return None
        if "data" in response and response["data"] is not None and "message_id" in response["data"]:
            log_func('INFO', 'OneBot', "Successfully sent private message")
            return response["data"]["message_id"]
        log_func('ERROR', 'OneBot', "Failed to send private message")
        return None

    async def get_group_info(self, group_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Getting group info of group:", group_id)
        json_data = {
            "action": "get_group_info",
            "params": {
                "group_id": group_id,
                "no_cache": True
            },
        }
        response = await self._make_request(json_data)
        if "data" in response and response["data"] is not None:
            log_func('INFO', 'OneBot', "Successfully got group info")
            return response["data"]
        log_func('ERROR', 'OneBot', "Failed to get group info")
        return None

    async def withdraw_message(self, message_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        if message_id is None:
            return None
        log_func('INFO', 'OneBot', "Withdrawing message:", message_id)
        json_data = {
            "action": "delete_msg",
            "params": {
                "message_id": message_id
            },
        }
        response = await self._make_request(json_data)
        if "status" in response:
            if response["status"] == "ok":
                log_func('INFO', 'OneBot', "Withdraw successfully")
                return True
        log_func('ERROR', 'OneBot', "Failed to withdraw message")
        return None

    async def set_group_ban(self, group_id, user_id, duration):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func('INFO', 'OneBot', "Banning user:", user_id)
        json_data = {
            "action": "set_group_ban",
            "params": {
                "group_id": group_id,
                "user_id": user_id,
                "duration": duration
            },
        }
        response = await self._make_request(json_data)
        if "status" in response:
            if response["status"] == "ok":
                log_func('INFO', 'OneBot', "Successfully banned user")
                return True
        log_func('ERROR', 'OneBot', "Failed to ban user")
        return None
