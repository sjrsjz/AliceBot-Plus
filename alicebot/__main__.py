import asyncio
import sys
import pathlib
import websockets
import json
import fJson as fjson
from typing import Optional
import copy
import threading
import time
import traceback
import psutil
from rich.text import Text

project_root = str(pathlib.Path(__file__).parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

from interface import TUI, WebUI

def default_log_func(level, entity, *args, **kwargs):
    print(f"[{level}][{entity}]", *args, **kwargs)

_log_func = default_log_func


def log_func(level = 'INFO', entity = 'System', *args, **kwargs):
    global _log_func
    if _log_func:
        _log_func(level, entity, *args, **kwargs)
    else:
        if default_log_func is not None:
            default_log_func(f"[{level}][{entity}]", *args, **kwargs)
        else:
            print(f"[{level}][{entity}]", *args, **kwargs)


onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "onebot"), log_func=log_func)
onebot_api_module = onebot_package.load_module("api", hot_reload=True, log_func=log_func)

bot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "entity"), log_func=log_func)
bot_module = bot_package.load_module("bot", log_func=log_func)

@fjson.DataClass
class ProtocolConfig:
    def __init__(self, ws_url: str = "ws://127.0.0.1:8080", webui_port: int = 8001):
        self.ws_url = ws_url
        self.webui_port = webui_port

    def load(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            data = self.load_json(f.read())
            self.ws_url = data.ws_url
            self.webui_port = data.webui_port
    def save(self, config_path: str):
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(self.json(indent=4, multi_line=True))

protocol_config = ProtocolConfig()

if not pathlib.Path(__file__).parent.exists():
    pathlib.Path(__file__).parent.mkdir()

try:
    protocol_config.load(str(pathlib.Path(__file__).parent / "config" / "protocol.json"))
except Exception as e:
    log_func('ERROR', 'Config', f"Failed to load protocol config: {e}")
    log_func('INFO', 'Config', "Creating default protocol config...")
    default_config = ProtocolConfig()
    default_config.save(str(pathlib.Path(__file__).parent / "config" / "protocol.json"))
    log_func('INFO', 'Config', "Default protocol config created, please configure the protocol and restart the program.")
    sys.exit(0)


close_event = asyncio.Event()


class ExitException(Exception):
    pass


class Status:
    def __init__(self, loop=None):
        self.running_tasks = []
        self.cpu_percent = 0
        self.memory_percent = 0
        self.start_time = time.time()
        self.task_count = 0
        self.loop = loop
        self.bot_tasks = []

    def update_task_count(self):
        # 获取当前事件循环
        # 获取所有正在运行的任务
        all_tasks = asyncio.all_tasks(self.loop)
        # 过滤掉已完成的任务
        running_tasks = [task for task in all_tasks if not task.done()]
        self.task_count = len(running_tasks)


async def process_message(ws, Bots, echo_pool, status: Status):
    while not close_event.is_set():
        timeout_count = 0
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=10.0)
            message = json.loads(message)
            timeout_count = 0

            if "status" in message and "echo" in message:
                echo_pool.echo_dict[message["echo"]] = message
                continue
            if message["post_type"] == "meta_event" and message["meta_event_type"] == "heartbeat":
                # log_func('INFO', 'Websocket', "Received heartbeat")
                continue

            async def bot_process(processor):
                task = asyncio.create_task(processor(ws, copy.deepcopy(message)))
                task_info = {
                    "task": task,
                    "bot": bot,
                    "message": copy.deepcopy(message),
                    "start_time": time.time(),
                    "websocket": ws
                }
                status.bot_tasks.append(task_info)

                def task_done_callback(task):
                    try:
                        # 获取任务结果，这会重新引发任何未处理的异常
                        task.result()

                        # 如果没有异常，记录成功信息
                        for idx in range(len(status.bot_tasks)):
                            if status.bot_tasks[idx]["task"] == task:
                                log_func('INFO', 'Task', "Task completed:",
                                        status.bot_tasks[idx]['task'].get_name(),
                                        "Time:", time.time() - status.bot_tasks[idx]['start_time'])
                                status.bot_tasks.pop(idx)
                                break

                    except asyncio.CancelledError:
                        log_func('WARN', 'Task', "Task was cancelled")
                    except Exception as e:
                        log_func('ERROR', 'Task', "Task failed with error:", e, '\n' + traceback.format_exc())
                    finally:
                        # 确保任务从列表中移除
                        for idx in range(len(status.bot_tasks)):
                            if status.bot_tasks[idx]["task"] == task:
                                status.bot_tasks.pop(idx)
                                break

                task.add_done_callback(task_done_callback)



            if message["post_type"] == "message" and message["message_type"] == "group":
                for bot in Bots:
                    await bot_process(bot.receive_group_message)
            elif message["post_type"] == "notice":
                notice_type = message.get("notice_type", "unknown")
                sub_type = message.get("sub_type", "unknown")
                
                log_func('INFO', 'Notice', f"Received {notice_type}/{sub_type} notice")
                
                if notice_type == "notify" and sub_type == "poke":
                    for bot in Bots:
                        await bot_process(bot.receive_poke_notice)

            else:
                log_func('WARN', 'Websocket', "Unsupported message type: ", message)
        except websockets.exceptions.ConnectionClosedError:
            log_func('ERROR', 'Websocket', "Connection closed in message processor")
            break
        except asyncio.TimeoutError:
            log_func('WARN', 'Websocket', "Message processing timeout")
            timeout_count += 1
            if timeout_count > 10:
                log_func('ERROR', 'Websocket', "Cannot hold connection! is the bot backend still alive? Reconnecting...")
                break
            continue
        except Exception as e:
            log_func('ERROR', 'Websocket', "Error in message processor: ", e)
            await asyncio.sleep(1)


global_websocket : websockets.WebSocketClientProtocol = None

def init(status: Status):
    def update_status(width):
        text = Text()
        text.append("[Bot", "bold")

        # 计算并显示运行时间
        uptime = time.time() - status.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        text.append("|", "bold")
        text.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}", "bold green")
        text.append("]", "bold")

        # 显示CPU信息
        text.append("[CPU ", "bold")
        if status.cpu_percent > 50:
            text.append(f"{status.cpu_percent}%", "bold red")
        elif status.cpu_percent > 30:
            text.append(f"{status.cpu_percent}%", "bold yellow")
        else:
            text.append(f"{status.cpu_percent}%", "bold green")

        # 显示内存信息
        text.append(" MEM ", "bold")
        if status.memory_percent > 50:
            text.append(f"{status.memory_percent}%", "bold red")
        elif status.memory_percent > 30:
            text.append(f"{status.memory_percent}%", "bold yellow")
        else:
            text.append(f"{status.memory_percent}%", "bold green")
        text.append("]", "bold")

        # 显示运行任务数
        text.append("[Tasks ", "bold")
        if status.task_count > 10:
            text.append(f"{status.task_count}", "bold red")
        elif status.task_count > 5:
            text.append(f"{status.task_count}", "bold yellow")
        else:
            text.append(f"{status.task_count}", "bold green")
        text.append("]", "bold")

        return text

    def close_server():
        close_event.set()
        global _log_func
        _log_func = default_log_func
        log_func('WARN', 'System', "Received close signal")
        if global_websocket:
            # 强制关闭websocket连接
            log_func('INFO', 'System', "Closing websocket connection")
            global_websocket.transport.abort()
            global_websocket.transport.close()
            log_func('INFO', 'System', "Websocket connection closed")

    # 新建一个日志文件在 logs/time.log
    log_file = pathlib.Path(__file__).parent / "logs" / f"{time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    tui = TUI.RichTUI(update_status, close_server, open(log_file, 'a', encoding='utf-8'))

    def update_machine_status():
        while not tui.close_signal:
            status.cpu_percent = psutil.cpu_percent(interval=1)
            status.memory_percent = psutil.virtual_memory().percent
            status.update_task_count()  # 更新协程数量
            time.sleep(1)

    update_machine_status_thread = threading.Thread(target=update_machine_status, daemon=True)
    update_machine_status_thread.start()
    tui.run_TUI_thread()

    global _log_func
    _log_func = tui.log
    return tui


global_status = Status()


async def server(ws_url=protocol_config.ws_url):
    global_status.loop = asyncio.get_event_loop()
    tui = init(global_status)
    async def log_provider():
        async def get_task_info():
            info = {}
            info["cpu_percent"] = global_status.cpu_percent
            info["memory_percent"] = global_status.memory_percent
            info["running_tasks"] = []
            current_time = time.time()
            for task in global_status.bot_tasks:
                tmp = {}
                name = task["task"].get_name()
                tmp["task_name"] = f"{name}"
                tmp["task_start_time"] = task["start_time"]
                tmp["task_duration"] = current_time - task["start_time"]
                tmp["message"] = task["message"]
                info["running_tasks"].append(tmp)
            return info

        return {"log_text": tui.get_frame_buffer, "tasks_info": get_task_info}
    webui = WebUI.WebUI(protocol_config.webui_port, log_provider, log_func)

    log_func('INFO', 'System', "Booting up...")

    await webui.run()

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

            log_func('INFO', 'Websocket', "Received response")
            if "self_id" in response:
                bot_qq = response["self_id"]
                log_func('INFO', 'Websocket', "Connected to bot backend successfully")
                for bot in Bots:
                    bot.bot_qq = bot_qq
                    await bot.create(ws)

                await process_message(ws, Bots, echo_pool, global_status)
            else:
                log_func('ERROR', 'Websocket', "Failed to connect to bot backend: ", response)
                await asyncio.sleep(5)
                continue
        except websockets.exceptions.ConnectionClosedError:
            log_func('ERROR', 'Websocket', "Connection closed, reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            log_func('INFO', 'Websocket', "Reconnecting...")
        except Exception as e:
            log_func('ERROR', 'Websocket', f"Error: {str(e)}, reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            log_func('INFO', 'Websocket', "Reconnecting...")

    log_func('INFO', 'System', "Server is shutting down...")
    echo_pool.close_event.set()
    for bot in Bots:
        await bot.destroy(ws)

    await webui.exit()

async def cleanup():
    log_func("INFO", "System", "Cleaning up...")
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    for task in tasks:
        task.cancel()

    try:
        await asyncio.wait(tasks, timeout=5.0)
    except asyncio.TimeoutError:
        log_func("WARN", "System", "Timeout waiting for tasks to cancel")
    except Exception as e:
        log_func("ERROR", "System", f"Error during cleanup: {e}")

    try:
        loop = asyncio.get_event_loop()
        await loop.shutdown_asyncgens()
        if sys.platform == "win32":
            loop._signal_handlers.clear()
    except Exception as e:
        log_func("ERROR", "System", f"Error during event loop cleanup: {e}")

    log_func("INFO", "System", "Cleanup completed")


def signal_handler():
    log_func('WARN', 'System', "Received shutdown signal")
    close_event.set()


async def main():
    try:

        await server(ws_url=protocol_config.ws_url)
    except Exception as e:
        log_func('ERROR', 'System', f'Error in main: {e}')
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
        log_func('ERROR', 'System', "KeyboardInterrupt received")
    finally:
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()

        # 运行剩余任务直到完成
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        log_func('INFO', 'System', "Event loop closed")
