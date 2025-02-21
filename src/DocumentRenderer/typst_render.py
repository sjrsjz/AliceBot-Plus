import typst
import sys
import os
import asyncio
import time
def render(typst_text: str) -> str:
    if sys.platform == 'win32':
        # Windows
        # tmp file
        tmp_file = 'tmp/' + str(time.time()) + '.typ'
        try:
            if not os.path.exists('tmp'):
                os.makedirs('tmp')
            with open(tmp_file, 'w', encoding="utf-8") as f:
                f.write(typst_text)
        except Exception as e:
            os.remove(tmp_file)
            print("[Typst Renderer] Error:",e)
            raise e
        # render
        try:
            img = typst.compile(tmp_file,format='png')
            os.remove(tmp_file)
        except Exception as e:
            os.remove(tmp_file)
            print("[Typst Renderer] Error:",e)
            raise e
        # remove tmp file
        return img
    elif sys.platform == 'linux':
        # Linux
        # write to /dev/shm
        # tmp file

        tmp_file = '/dev/shm/typst_tmp_' + str(time.time()) + '.typ'        
        try:
            if not os.path.exists('/dev/shm'):
                os.makedirs('/dev/shm')
            with open(tmp_file, 'w', encoding="utf-8") as f:
                f.write(typst_text)
        except Exception as e:
            os.remove(tmp_file)
            print("[Typst Renderer] Error:",e)
            raise e
        # render
        try:
            img = typst.compile(tmp_file,format='png')
            os.remove(tmp_file)
        except Exception as e:
            os.remove(tmp_file)
            print("[Typst Renderer] Error:",e)
            raise e
        return img
    else:
        raise Exception('Unsupported platform')
    
async def render_async(typst_text: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, render, typst_text)