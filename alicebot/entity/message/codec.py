import base64
import aiohttp
import pathlib
import sys
project_root = str(pathlib.Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader
aibackend_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent.parent.parent / "aibackend"))
gemini = aibackend_package.load_module("gemini")
async def encode_message_to_CQ(message):
    encoded_message = ""
    for x in message:
        if x["type"] == "text":
            encoded_message += x["data"]["text"]
        else:
            encoded_message += f"[CQ:{x['type']},"
            for key, value in x["data"].items():
                if key != "type":
                    encoded_message += f"{key}={value},"
            encoded_message = encoded_message[:-1] + "]"
    return encoded_message
async def encode_message_to_CQ_without_At_self(message, bot_qq):
    encoded_message = ""
    for x in message:
        if x["type"] == "text":
            encoded_message += x["data"]["text"]
        else:
            if x["type"] == "at" and x["data"]["qq"] == str(bot_qq):
                continue
            encoded_message += f"[CQ:{x['type']},"
            for key, value in x["data"].items():
                if key != "type":
                    encoded_message += f"{key}={value},"
            encoded_message = encoded_message[:-1] + "]"
    return encoded_message

async def encode_message_to_CQ_without_At_self_and_Image(message, bot_qq):
    encoded_message = ""
    for x in message:
        if x["type"] == "text":
            encoded_message += x["data"]["text"]
        else:
            if x["type"] == "at" and x["data"]["qq"] == str(bot_qq):
                continue
            if x["type"] == "image":
                if "base64" in x["data"]:
                    img = x["data"]["base64"]
                    # decode
                    img = base64.b64decode(img)
                    tag = await gemini.image_to_text(img)
                    encoded_message += f" <Image:prompt=\"{tag}\"> "
                elif "url" in x["data"]:
                    url = x["data"]["url"]
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as response:
                            img = await response.read()
                    tag = await gemini.image_to_text(img)
                    encoded_message += f" <Image:prompt=\"{tag}\"> "
                continue
            encoded_message += f"[CQ:{x['type']},"
            for key, value in x["data"].items():
                if key != "type":
                    encoded_message += f"{key}={value},"
            encoded_message = encoded_message[:-1] + "]"
    return encoded_message

async def encode_message_to_CQ_without_At_self_and_Image_tag(message, bot_qq):
    encoded_message = ""
    for x in message:
        if x["type"] == "text":
            encoded_message += x["data"]["text"]
        else:
            if x["type"] == "at" and x["data"]["qq"] == str(bot_qq):
                continue
            if x["type"] == "image":
                if "base64" in x["data"]:
                    encoded_message += f" [图片] "
                elif "url" in x["data"]:
                    url = x["data"]["url"]
                    encoded_message += f" [图片]({url}) "
                continue
            encoded_message += f"[CQ:{x['type']},"
            for key, value in x["data"].items():
                if key != "type":
                    encoded_message += f"{key}={value},"
            encoded_message = encoded_message[:-1] + "]"
    return encoded_message
async def decode_CQ_to_message(message):
    decoded_message = []
    i = 0
    while i < len(message):
        if message[i] == "[":
            j = i + 1
            while j < len(message) and message[j] != "]":
                j += 1
            if j < len(message):
                cq_message = message[i + 1:j]
                cq_message = cq_message.split(",")
                cq_type = cq_message[0]
                cq_data = {}
                for x in cq_message[1:]:
                    try:
                        key, value = x.split("=", 1)
                    except:
                        key = x
                        value = ""
                    cq_data[key] = value
                # remove "CQ:" prefix
                if cq_type.startswith("CQ:"):
                    cq_type = cq_type[3:]
                    decoded_message.append({"type": cq_type, "data": cq_data})
                else:
                    decoded_message.append({"type": "text", "data": {"text": "[" + message[i + 1:j] + "]"}})
                i = j + 1
            else:
                if str(message[i:]) != "":
                    decoded_message.append({"type": "text", "data": {"text": str(message[i:])}})
                break
        else:
            j = i + 1
            while j < len(message) and message[j] != "[":
                j += 1
            if str(message[i:j]) != "":
                decoded_message.append({"type": "text", "data": {"text": str(message[i:j])}})
            i = j
    return decoded_message