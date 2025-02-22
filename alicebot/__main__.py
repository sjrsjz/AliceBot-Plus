import asyncio
import sys
import pathlib
import websockets
import json
from typing import Optional
import copy
import threading
import time
import math
import psutil
from rich.text import Text

project_root = str(pathlib.Path(__file__).parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

from interface import TUI

_log_func = print
def log_func(text, *args, **kwargs):
    global _log_func
    if _log_func:
        _log_func(text, *args, **kwargs)
    else:
        print(text, *args, **kwargs)

onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "onebot"), log_func=log_func)
onebot_api_module = onebot_package.load_module("api", hot_reload=True, log_func=log_func)

bot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "entity"), log_func=log_func)
bot_module = bot_package.load_module("bot", log_func=log_func)

ws_url = "ws://192.168.31.116:8080"

close_event = asyncio.Event()

class ExitException(Exception):
    pass


async def process_message(ws, Bots, echo_pool):
    while not close_event.is_set():
        try:
            message = json.loads(await ws.recv())

            if "status" in message and "echo" in message:
                echo_pool.echo_dict[message["echo"]] = message
                continue
                        
            if message["post_type"] == "meta_event" and message["meta_event_type"] == "heartbeat":
                log_func("[🟨|Websocket]Received heartbeat")
                continue
            #print("[🟨|Websocket]Received message: ", message)
            if message["post_type"] == "message" and message["message_type"] == "group":
                for bot in Bots:
                    # 改用 asyncio.ensure_future 替代 create_task
                    asyncio.ensure_future(bot.receive_group_message(ws, copy.deepcopy(message)))
            else:
                log_func("[🟥|Websocket]Unsupported message type: ", message)
        except websockets.exceptions.ConnectionClosedError:
            log_func("[🟥|Websocket]Connection closed in message processor")
            break
        except Exception as e:
            log_func("[🟥|Websocket]Error in message processor: ", e)
            await asyncio.sleep(1)

class Status:
    def __init__(self):
        self.running_tasks = []
        self.cpu_percent = 0
        self.memory_percent = 0

global_websocket = None
def init(status: Status, loop):

    def update_status(width):
        text = Text()
        text.append("[Bot]", "bold")
        text.append("[CPU ", "bold")
        if status.cpu_percent > 50:
            text.append(f"{status.cpu_percent}%", "bold red")
        elif status.cpu_percent > 30:
            text.append(f"{status.cpu_percent}%", "bold yellow")
        else:
            text.append(f"{status.cpu_percent}%", "bold green")
        text.append(" MEM ", "bold")
        if status.memory_percent > 50:
            text.append(f"{status.memory_percent}%", "bold red")
        elif status.memory_percent > 30:
            text.append(f"{status.memory_percent}%", "bold yellow")
        else:
            text.append(f"{status.memory_percent}%", "bold green")
        text.append("]Running Tasks [", "bold")
        if len(status.running_tasks) > 5:
            text.append(f"{len(status.running_tasks)}", "bold red")
        elif len(status.running_tasks) > 3:
            text.append(f"{len(status.running_tasks)}", "bold yellow")
        else:
            text.append(f"{len(status.running_tasks)}", "bold green")
        text.append("]|")
        current_time = time.time()
        pressure = int((1 - math.exp(-sum([current_time - task["start_time"] for task in status.running_tasks]) / 60)) * 100)
        if pressure > 50:
            color = "on black bold red"
        elif pressure > 30:
            color = "on black bold yellow"
        else:
            color = "on black bold green"
        text.append("█" * int((width - len(text)) * pressure / 100), color)
        return text
    
    def close_server():
        close_event.set()
        log_func("[🟧|System]Received close signal")
        if global_websocket:
            global_websocket.transport.close()

    tui = TUI.RichTUI(update_status, close_server)
    def update_machine_status():
        while not tui.close_signal:
            status.cpu_percent = psutil.cpu_percent(interval=1)
            status.memory_percent = psutil.virtual_memory().percent
            time.sleep(1)

    update_machine_status_thread = threading.Thread(target=update_machine_status, daemon=True)
    update_machine_status_thread.start()
    tui.run_TUI_thread()

    global _log_func
    _log_func = tui.print
    return tui



global_status = Status()
async def server():
    tui = init(global_status, asyncio.get_event_loop())
    log_func("[🟧|System]Booting up...")
    echo_pool = onebot_api_module.EchoPool()
    Bots = [bot_module.Bot(echo_pool)]
    ws: Optional[websockets.WebSocketClientProtocol] = None

    while not close_event.is_set():
        try:
            ws = await websockets.connect(ws_url, ping_interval=None, ping_timeout=None)
            global global_websocket
            global_websocket = ws

            response = await ws.recv()
            response = json.loads(response)

            log_func("[🟨|Websocket]Received response")
            if "self_id" in response:
                bot_qq = response["self_id"]
                log_func("[🟩|Websocket]Connected to bot backend successfully")
                group_list = json.loads(await onebot_api_module.OneBotAPI(echo_pool).get_bot_group_list(ws, False))
                log_func("[🟩|Websocket]Bot group list: length", len(group_list['data']))

                for bot in Bots:
                    bot.bot_qq = bot_qq
                    await bot.create(ws)

                await process_message(ws, Bots, echo_pool)
            else:
                log_func("[🟥|Websocket]Failed to connect to bot backend: ", response)
                await asyncio.sleep(5)
                continue
        except websockets.exceptions.ConnectionClosedError:
            log_func("[🟥|Websocket]Connection closed, reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            log_func("[🟨|Websocket]Reconnecting...")
        except Exception as e:
            log_func(f"[🟥|Websocket]Error: {str(e)}, reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            log_func("[🟨|Websocket]Reconnecting...")

    log_func("[🟧|System]Server is shutting down...")
    echo_pool.close_event.set()
    for bot in Bots:
        await bot.destroy(ws)
    global _log_func
    _log_func = print
async def cleanup():
    log_func("[🟧|System]Cleaning up...")
    tasks = [task for task in asyncio.all_tasks() 
             if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log_func("[🟧|System]Cleanup completed")

def signal_handler():
    log_func("\n[🟧|System]Received shutdown signal")
    close_event.set()

async def main():
    try:
        
        await server()
    except Exception as e:
        log_func(f'[🟥|System]Error in main: {e}')
    finally:
        await cleanup()

if __name__ == '__main__':
    try:
        if sys.platform == 'win32':
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        log_func("\n[🟥|System]KeyboardInterrupt received")
    finally:
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()
        
        # 运行剩余任务直到完成
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        log_func("[🟥|System]Event loop closed")