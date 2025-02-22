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
    def __init__(self, echo_pool=None):
        self.echo_pool = echo_pool

    async def get_stranger_info(self, ws, user_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Getting stranger info:", user_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "get_stranger_info",
            "params": {
                "user_id": user_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "data" in response and response["data"] is not None:
            log_func("[🟩|OneBot]Successfully got stranger info")
            return response["data"]
        log_func("[🟥|OneBot]Failed to get stranger info")
        return None

    async def get_bot_group_list(self, ws, async_mode=True):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Getting bot group list")
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "get_group_list",
            "params": {},
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        if not async_mode:
            return await ws.recv()
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "data" in response and response["data"] is not None:
            log_func("[🟩|OneBot]Successfully got bot group list")
            return response["data"]
        log_func("[🟥|OneBot]Failed to get bot group list")
        return None

    async def get_member_list(self, ws, group_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Getting member list of group:", group_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "get_group_member_list",
            "params": {
                "group_id": group_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))

        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "data" in response and response["data"] is not None:
            log_func("[🟩|OneBot]Successfully got member list")
            return response["data"]
        log_func("[🟥|OneBot]Failed to get member list")
        return None

    async def send_group_message(self, ws, group_id, message, auto_escape=False):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Sending group message to group:", group_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": message,
                "auto_escape": auto_escape
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                log_func("[🟩|OneBot]Message sent successfully")
            else:
                log_func("[🟥|OneBot]Failed to send group message")
        if response is None:
            return None
        if "data" in response and response["data"] is not None and "message_id" in response["data"]:
            log_func("[🟩|OneBot]Successfully sent group message")
            return response["data"]["message_id"]
        log_func("[🟥|OneBot]Failed to send group message")
        return None

    async def send_group_message_separate_audio(self, ws, group_id, message, auto_escape=False):
        # 剥离音频消息单独发送
        other_message = []
        for i in message:
            if i["type"] == "record":
                if other_message:
                    await OneBotAPI.send_group_message(ws, self.echo_pool, group_id, other_message, auto_escape)
                    other_message = []
                await OneBotAPI.send_group_message(ws, self.echo_pool, group_id, [i], auto_escape)
            else:
                other_message.append(i)
        if other_message:
            await OneBotAPI.send_group_message(ws, self.echo_pool, group_id, other_message, auto_escape)

    async def send_private_message(self, ws, user_id, message, auto_escape=False):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Sending private message to user:", user_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": message,
                "auto_escape": auto_escape
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        log_func("[Lagrange Core]Response:", response)
        if "status" in response:
            if response["status"] == "ok":
                log_func("[OneBot]Message sent successfully")
            else:
                log_func("[OneBot]Failed to send message")
        if response is None:
            return None
        if "data" in response and response["data"] is not None and "message_id" in response["data"]:
            log_func("[🟩|OneBot]Successfully sent private message")
            return response["data"]["message_id"]
        log_func("[🟥|OneBot]Failed to send private message")
        return None

    async def get_group_info(self, ws, group_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Getting group info of group:", group_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "get_group_info",
            "params": {
                "group_id": group_id,
                "no_cache": True
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "data" in response and response["data"] is not None:
            log_func("[🟩|OneBot]Successfully got group info")
            return response["data"]
        log_func("[🟥|OneBot]Failed to get group info")
        return None

    async def withdraw_group_message(self, ws, message_id):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        if message_id is None:
            return None
        log_func("[🟨|OneBot]Withdrawing message:", message_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "delete_msg",
            "params": {
                "message_id": message_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                log_func("[🟩|OneBot]Withdraw successfully")
            else:
                log_func("[🟥|OneBot]Failed to withdraw message")
        log_func("[🟥|OneBot]Failed to withdraw message")
        return None

    async def set_group_ban(self, ws, group_id, user_id, duration):
        if self.echo_pool.echo_dict is None: raise Exception("Echo dict not set")
        log_func("[🟨|OneBot]Banning user:", user_id)
        self.echo_pool.echo_counter += 1
        self_echo = str(self.echo_pool.echo_counter)
        json_data = {
            "action": "set_group_ban",
            "params": {
                "group_id": group_id,
                "user_id": user_id,
                "duration": duration
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in self.echo_pool.echo_dict and not self.self.echo_pool.close_event.is_set():
            await asyncio.sleep(0.1)
        response = self.echo_pool.echo_dict[self_echo]
        del self.echo_pool.echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                log_func("[🟩|OneBot]Successfully banned user")
            else:
                log_func("[🟥|OneBot]Failed to ban user")
        log_func("[🟥|OneBot]Failed to ban user")
        return None
