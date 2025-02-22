from alicebot.loader import moduleloader
import pathlib
import asyncio

from typing import Callable, Any
log_func: Callable[[Any], None]


prompts_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent) + "/prompts", log_func=log_func)
template = prompts_package.load_module("template", log_func=log_func)

document_renderer_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent) + "/DocumentRenderer", log_func=log_func)
renderer = document_renderer_package.load_module("renderer", log_func=log_func)

if __name__ == "__main__":
    #template.__test__()
    async def test():
        await renderer.__test__()
    asyncio.run(test())
