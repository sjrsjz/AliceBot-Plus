from src.loader import moduleloader
import pathlib
import asyncio
prompts_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent) + "/prompts")
template = prompts_package.load_module("template")

document_renderer_package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent) + "/DocumentRenderer")
renderer = document_renderer_package.load_module("renderer")

if __name__ == "__main__":
    #template.__test__()
    async def test():
        await renderer.__test__()
    asyncio.run(test())
