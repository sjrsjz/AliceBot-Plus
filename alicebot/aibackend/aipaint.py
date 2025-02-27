import pathlib
import sys
import aiohttp
import enum
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


class ImageSize(enum.Enum):
    TALL = "720x1440"
    WIDE = "1440x720"
    SQUARE = "1024x1024"


class ImageStyle(enum.Enum):
    ANIME = "anime"
    PHOTO = "photo"


class APILevel:
    FREE = "free"
    PRO = "pro"


async def generate_image_siliconflow(
    prompt, size: ImageSize, style: ImageStyle, api_level: APILevel, seed=None, step=20
):
    url = "https://api.siliconflow.cn/v1/images/generations"

    if style == ImageStyle.ANIME:
        prompt = f"generate an anime style image for the following prompts: {prompt}"
    elif style == ImageStyle.PHOTO:
        prompt = f"generate a photo-realistic image for the following prompts: {prompt}"
    else:
        raise ValueError("Invalid image style")

    if api_level == APILevel.FREE:
        model = "black-forest-labs/FLUX.1-schnell"
    elif api_level == APILevel.PRO:
        model = "black-forest-labs/FLUX.1-dev"
    else:
        raise ValueError("Invalid API level")

    payload = {
        "model": model,
        "prompt": prompt,
        "num_inference_steps": step,
        "image_size": size.value,
    }

    headers = {
        "Authorization": f"Bearer {package['apikey'].config.key_siliconflow()}",
        "Content-Type": "application/json",
    }

    if seed is not None:
        payload["seed"] = seed

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()
            image_url = result["images"][0]["url"]

            image_data = await session.get(image_url)
            return await image_data.read()


async def generate_image(
    prompt, size: ImageSize, style: ImageStyle, api_level: APILevel, seed=None, step=20
):
    return await generate_image_siliconflow(prompt, size, style, api_level, seed, step)
