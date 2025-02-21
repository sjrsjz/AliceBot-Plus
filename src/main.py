import asyncio
import sys
import pathlib
import websockets
import json
from typing import Optional


project_root = str(pathlib.Path(__file__).parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

onebot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "onebot"))
onebot_api_module = onebot_package.load_module("api")
onebot_api = onebot_api_module.OneBotAPI()

bot_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent / "entity"))
bot_module = bot_package.load_module("bot")

ws_url = "ws://192.168.31.116:8080"

close_event = asyncio.Event()

class ExitException(Exception):
    pass


async def process_message(ws, Bots):
    while not close_event.is_set():
        try:
            message = json.loads(await ws.recv())
            if message["post_type"] == "meta_event" and message["meta_event_type"] == "heartbeat":
                print("[🟨|Websocket]Received heartbeat")
                continue
            print("[🟨|Websocket]Received message: ", message)
            if message["post_type"] == "message" and message["message_type"] == "group":
                for bot in Bots:
                    # 改用 asyncio.ensure_future 替代 create_task
                    asyncio.ensure_future(bot.receive_group_message(ws, message))
            else:
                print("[🟥|Websocket]Unsupported message type: ", message)
        except websockets.exceptions.ConnectionClosedError:
            print("[🟥|Websocket]Connection closed in message processor")
            break
        except Exception as e:
            print("[🟥|Websocket]Error in message processor: ", e)
            await asyncio.sleep(1)

async def server():
    print("[System]Booting up...")
    Bots = [bot_module.Bot()]
    ws: Optional[websockets.WebSocketClientProtocol] = None

    while not close_event.is_set():
        try:
            ws = await websockets.connect(ws_url, ping_interval=None, ping_timeout=None)
            response = await ws.recv()
            response = json.loads(response)

            print("[🟨|Websocket]Received response")
            if "self_id" in response:
                bot_qq = response["self_id"]
                print("[🟩|Websocket]Connected to bot backend successfully")
                group_list = json.loads(await onebot_api.get_bot_group_list(ws, False))
                print("[🟩|Websocket]Bot group list: length", len(group_list['data']))

                for bot in Bots:
                    bot.bot_qq = bot_qq
                    await bot.create(ws)

                await process_message(ws, Bots)
            else:
                print("[🟥|Websocket]Failed to connect to bot backend: ", response)
                await asyncio.sleep(5)
                continue

        except websockets.exceptions.ConnectionClosedError:
            print("[🟥|Websocket]Connection closed, reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            print("[🟨|Websocket]Reconnecting...")
        except Exception as e:
            print("[🟥|Websocket]Error: ", e, "reconnect after 5 seconds")
            if ws:
                await ws.close()
            await asyncio.sleep(5)
            print("[🟨|Websocket]Reconnecting...")

    print("[System]Server is shutting down...")

async def cleanup():
    print("[System]Cleaning up...")
    tasks = [task for task in asyncio.all_tasks() 
             if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("[System]Cleanup completed")

def signal_handler():
    print("\n[System]Received shutdown signal")
    close_event.set()

async def main():
    try:
        
        await server()
    except Exception as e:
        print(f'[System]Error in main: {e}')
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
        print("\n[System]KeyboardInterrupt received")
    finally:
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()
        
        # 运行剩余任务直到完成
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        print("[System]Event loop closed")