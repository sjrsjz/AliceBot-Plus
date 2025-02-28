import pathlib
import sys
import aiohttp
import enum
import base64
import json
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


config_path = pathlib.Path(__file__).parent / "config"
config_path.mkdir(exist_ok=True)

class SwarmConfig:

    def __init__(self, swarm_config):
        if not swarm_config.exists():
            with swarm_config.open("w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "swarm_api_address": "https://localhost:7801",
                            "swarm_anime_model": "text-to-image-anime",
                            "swarm_photo_model": "text-to-image-photo",
                            "swarm_default_model": "text-to-image",
                            "swarm_anime_negative_prompt": "score_4,score_5,score_3,score_2,score_1,3D,realistic,monochrome,source_pony,source_furry,bad hands,"
                            "low quality,distorted,worst quality,compression artifacts,artist name,watermark,duplicate,beginner,"
                            "symmetrical,glitch,overexposed,text,extra fingers,missing fingers,fused fingers,bad-contrast,mutated legs,"
                            "mutated hands,boring_sdxl_v1,zPDXLxxx-neg,NEGATIVE_HANDS,easynegative",
                            "swarm_photo_negative_prompt": "cartoon, anime, illustration, painting, drawing, art, sketch, oil painting, 3d render, blurry, deformed,"
                            "disfigured, bad anatomy, bad hands, missing fingers, extra limbs, extra fingers",
                        },
                        indent=4,
                    )
                )

        with swarm_config.open("r", encoding="utf-8") as f:
            self.swarm_config = json.load(f)

    def swarm_api_address(self):
        return self.swarm_config.get("swarm_api_address", "https://localhost:7801")

    def swarm_anime_model(self):
        return self.swarm_config.get("swarm_anime_model", "text-to-image-anime")

    def swarm_photo_model(self):
        return self.swarm_config.get("swarm_photo_model", "text-to-image-photo")

    def swarm_default_model(self):
        return self.swarm_config.get("swarm_default_model", "text-to-image")

    def swarm_anime_negative_prompt(self):
        return self.swarm_config.get("swarm_anime_negative_prompt", "score_4,score_5,score_3,score_2,score_1,3D,realistic,monochrome,source_pony,source_furry,bad hands,"
                        "low quality,distorted,worst quality,compression artifacts,artist name,watermark,duplicate,beginner,"
                        "symmetrical,glitch,overexposed,text,extra fingers,missing fingers,fused fingers,bad-contrast,mutated legs,")

    def swarm_photo_negative_prompt(self):
        return self.swarm_config.get("swarm_photo_negative_prompt", "cartoon, anime, illustration, painting, drawing, art, sketch, oil painting, 3d render, blurry, deformed,"
                        "disfigured, bad anatomy, bad hands, missing fingers, extra limbs, extra fingers")

swarm_config = SwarmConfig(config_path / "swarmui.json")


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


class SwarmAPI:
    client = None
    session = ""

    @classmethod
    async def initialize(cls):
        log_func("INFO", "SwarmAPI", "Initializing client")
        cls.client = aiohttp.ClientSession(
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        # 从配置中获取地址
        cls.address = swarm_config.swarm_api_address()
        log_func("INFO", "SwarmAPI", "Client initialized")

    @classmethod
    async def get_session(cls):
        log_func("INFO", "SwarmAPI", "Getting new session")
        async with cls.client.post(
            f"{cls.address}/API/GetNewSession", data="{}", timeout=5
        ) as response:
            session_data = await response.json()
            cls.session = session_data.get("session_id")
        log_func("INFO", "SwarmAPI", f"Got new session: {cls.session}")

    @classmethod
    async def run_with_session(
        cls, prompt, size: ImageSize, style: ImageStyle, seed=None, step=30
    ):
        log_func("INFO", "SwarmAPI", f"Generating image with prompt: {prompt}")
        if not cls.client:
            await cls.initialize()

        if not cls.session:
            await cls.get_session()

        # 根据样式调整提示词
        if style == ImageStyle.ANIME:
            final_prompt = f"2D,Anime,{prompt}"
            model = swarm_config.swarm_anime_model()
            negative_prompt = swarm_config.swarm_anime_negative_prompt()
        elif style == ImageStyle.PHOTO:
            final_prompt = f"photo-realistic,{prompt}"
            model = swarm_config.swarm_photo_model()
            negative_prompt = swarm_config.swarm_photo_negative_prompt()
        else:
            final_prompt = prompt
            model = swarm_config.swarm_default_model()
            negative_prompt = swarm_config.swarm_default_negative_prompt()

        width, height = size.value.split("x")
        width = int(width)
        height = int(height)


        request_data = {
            "images": 1,
            "session_id": cls.session,
            "donotsave": True,
            "prompt": final_prompt,
            "negativeprompt": negative_prompt,
            "model": model,
            "width": width,
            "height": height,
            "cfgscale": 7.5,
            "steps": step,
            "seed": -1 if seed is None else seed,
        }

        async with cls.client.post(
            f"{cls.address}/API/GenerateText2Image", json=request_data
        ) as response:
            generated = await response.json()

        if "error_id" in generated and generated["error_id"] == "invalid_session_id":
            await cls.get_session()
            log_func("INFO", "SwarmAPI", "Session expired, getting new session")
            return await cls.run_with_session(prompt, size, style, seed, step)

        log_func("INFO", "SwarmAPI", "Image generated")
        return generated["images"][0]

    @classmethod
    async def close(cls):
        if cls.client:
            await cls.client.close()
            cls.client = None

    @staticmethod
    async def check_is_available():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(swarm_config.swarm_api_address(), timeout=5) as response:
                    return response.status == 200
        except:
            return False

async def generate_image_swarm(
    prompt, size: ImageSize, style: ImageStyle, api_level: APILevel, seed=None, step=30
):
    """使用Swarm API生成图像"""
    try:
        api = SwarmAPI()
        await api.initialize()
        image_base64 = await api.run_with_session(prompt, size, style, seed, step)

        # 如果返回的是完整的data URL, 分割获取base64部分
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        # 将base64转换为二进制数据
        image_data = base64.b64decode(image_base64)
        await api.close()
        return image_data
    except Exception as e:
        log_func("ERROR", "SwarmAPI", f"Error generating image: {e}")
        raise


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

    log_func("INFO", "SiliconFlow API", f"Generating image with payload: {payload}")

    headers = {
        "Authorization": f"Bearer {package['apikey'].config.key_siliconflow()}",
        "Content-Type": "application/json",
    }

    if seed is not None:
        payload["seed"] = seed

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()
            log_func("INFO", "SiliconFlow API", f"Result: {result}")
            image_url = result["images"][0]["url"]
            image_data = await session.get(image_url)
            return await image_data.read()


async def generate_image(
    prompt, size: ImageSize, style: ImageStyle, api_level: APILevel, seed=None, step=20
):
    if await SwarmAPI.check_is_available():
        try:
            return await generate_image_swarm(prompt, size, style, api_level, seed, step = 30)  # 30 steps for better quality
        except Exception as e:
            log_func("ERROR", "SwarmAPI", f"Error generating image: {e}, falling back to SiliconFlow")
            return await generate_image_siliconflow(prompt, size, style, api_level, seed, step)
    else:
        return await generate_image_siliconflow(prompt, size, style, api_level, seed, step)
