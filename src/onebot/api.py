import asyncio
import json
class OneBotAPI:
    _echo_dict = {}
    _echo_counter = 0
    _crash_signal = False
    @staticmethod
    async def get_stranger_info(ws, user_id):
        OneBotAPI.echo_counter += 1
        self_echo = str(OneBotAPI.echo_counter)
        json_data = {
            "action": "get_stranger_info",
            "params": {
                "user_id": user_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "data" in response and response["data"] != None:
            return response["data"]
        return None

    @staticmethod
    async def get_bot_group_list(ws, async_mode=True):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
        json_data = {
            "action": "get_group_list",
            "params": {},
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        if not async_mode:
            return await ws.recv()
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "data" in response and response["data"] != None:
            return response["data"]
        return None

    @staticmethod
    async def get_member_list(ws, group_id):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
        json_data = {
            "action": "get_group_member_list",
            "params": {
                "group_id": group_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))

        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "data" in response and response["data"] != None:
            return response["data"]
        return None

    @staticmethod
    async def send_group_message(ws, group_id, message, auto_escape=False):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
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
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                print("[OneBot]Message sent successfully")
            else:
                print("[OneBot]Failed to send message")
        if response == None:
            return None
        if "data" in response and response["data"] != None and "message_id" in response["data"]:
            return response["data"]["message_id"]
        return None

    @staticmethod
    async def send_group_message_seperate_audio(ws, group_id, message, auto_escape=False):
        # 剥离音频消息单独发送
        other_message = []
        for i in message:
            if i["type"] == "record":
                if other_message != []:
                    await OneBotAPI.send_group_message(ws, group_id, other_message, auto_escape)
                    other_message = []
                await OneBotAPI.send_group_message(ws, group_id, [i], auto_escape)
            else:
                other_message.append(i)
        if other_message != []:
            await OneBotAPI.send_group_message(ws, group_id, other_message, auto_escape)

    @staticmethod
    async def send_private_message(ws, user_id, message, auto_escape=False):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
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
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        print ("[Lagrange Core]Response:",response)
        if "status" in response:
            if response["status"] == "ok":
                print("[OneBot]Message sent successfully")
            else:
                print("[OneBot]Failed to send message")
        if response == None:
            return None
        if "data" in response and response["data"] != None and "message_id" in response["data"]:
            return response["data"]["message_id"]
        return None
    @staticmethod
    async def get_group_info(ws, group_id):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
        json_data = {
            "action": "get_group_info",
            "params": {
                "group_id": group_id,
                "no_cache": True
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "data" in response and response["data"] != None:
            return response["data"]
        return None
    @staticmethod
    async def withdraw_group_message(ws, group_id, message_id):
        if message_id == None:
            return None
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
        json_data = {
            "action": "delete_msg",
            "params": {
                "message_id": message_id
            },
            "echo": self_echo
        }
        await ws.send(json.dumps(json_data))
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                print("[OneBot]Message withdrawn successfully")
            else:
                print("[OneBot]Failed to withdraw message")
        return None

    @staticmethod
    async def set_group_ban(ws, group_id, user_id, duration):
        OneBotAPI._echo_counter += 1
        self_echo = str(OneBotAPI._echo_counter)
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
        while self_echo not in OneBotAPI._echo_dict and not OneBotAPI._crash_signal:
            await asyncio.sleep(0.1)
        response = OneBotAPI._echo_dict[self_echo]
        del OneBotAPI._echo_dict[self_echo]
        if "status" in response:
            if response["status"] == "ok":
                print("[OneBot]User banned successfully")
            else:
                print("[OneBot]Failed to ban user")
        return None
    
    @staticmethod
    def destroy():
        OneBotAPI._crash_signal = True
