import pathlib
import sys
import aiohttp
from typing import Callable, Any

log_func: Callable[[Any], None]

if __name__ == "__main__":
    log_func = lambda *args: print(*args)

project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

package = moduleloader.ModuleLoader(
    str(pathlib.Path(__file__).parent), log_func=log_func
)
package.load_module("apikey", hot_reload=True, log_func=log_func)


async def text_to_speech_cosyvoice(text, emotion):
    url = "https://api.siliconflow.cn/v1/audio/speech"

    payload = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": "speak with emotion:" + emotion + "<|endofprompt|>" + text,
        "voice": "FunAudioLLM/CosyVoice2-0.5B:diana",
        "response_format": "mp3",
        "speed": 1,
        "gain": 0,
    }
    headers = {
        "Authorization": f"Bearer {package['apikey'].config.key_tts()}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            return await response.read()
