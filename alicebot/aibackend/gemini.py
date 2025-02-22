import google.generativeai as gai
from IPython.display import Markdown
import PIL.Image as pi
import io
import textwrap
import pathlib
import sys

from typing import Callable, Any

log_func: Callable[[Any], None]

project_root = str(pathlib.Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)
from loader import moduleloader

package = moduleloader.ModuleLoader(str(pathlib.Path(__file__).parent), log_func=log_func)
package.load_module("apikey", hot_reload=True, log_func=log_func)

def to_markdown(text):
    text = text.replace('•', '  *')
    return Markdown(textwrap.indent(text, '> ', predicate=lambda _: True))


async def image_to_text(image):
    try:
        log_func('INFO', 'Gemini', "Generating text from image[...")
        gai.configure(api_key=package['apikey'].config.key_gemini())
        model = gai.GenerativeModel('gemini-1.5-flash')
        response = await model.generate_content_async(["Only output what the Image is", pi.open(io.BytesIO(image))])
        log_func('INFO', 'Gemini', "text: ", response.text)
        return response.text
    except Exception as e:
        log_func('ERROR', 'Gemini', "Error: ", e)
        return "Error:" + str(e)
