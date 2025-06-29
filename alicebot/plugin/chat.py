# chat.py

import pathlib
import fJson as fjson
import time
import traceback
import base64
import os
import asyncio
import aiohttp
import random
import bs4  # BeautifulSoup for HTML parsing
from threading import Lock
from typing import Callable, Any, List, Optional
from bs4 import BeautifulSoup

log_func: Callable[[Any], None]
plugin_context: Any  # 插件上下文，由插件管理器传入

# --- All original package loaders remain unchanged ---
from loader import moduleloader

# ... (all your existing module loaders are here)
onebot_package = moduleloader.ModuleLoader(
    plugin_context.onebot_package_path, log_func=log_func
)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)
message_codec_package = moduleloader.ModuleLoader(
    plugin_context.message_codec_package_path, log_func=log_func
)
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func)
message_codec_package.load_module("context", hot_reload=True, log_func=log_func)
aibackend_package = moduleloader.ModuleLoader(
    plugin_context.aibackend_package_path, log_func=log_func
)
aibackend_package.load_module("gemini", hot_reload=True, log_func=log_func)
aibackend_package.load_module("tts", hot_reload=True, log_func=log_func)
aibackend_package.load_module("aipaint", hot_reload=True, log_func=log_func)
aibackend_package.load_module("apikey", hot_reload=True, log_func=log_func)
document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
document_renderer = document_renderer_package.load_module(
    "renderer", hot_reload=True, log_func=log_func
)
prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path, log_func=log_func
)
template = prompt_package.load_module("template", log_func=log_func)
example_prompt_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path / "example" / "character", log_func=log_func
)
example_prompt_package.load_module("Alice", hot_reload=True, log_func=log_func)
example_typeset_package = moduleloader.ModuleLoader(
    plugin_context.prompt_package_path / "example" / "typeset", log_func=log_func
)
example_typeset_package.load_module("QQBot", hot_reload=True, log_func=log_func)


# --- NEW: Agent-related imports from autogemini library ---
from autogemini.auto_stream_processor import create_cot_processor, CallbackMsgType
from autogemini.tool_code import DefaultApi
from autogemini.template import ToolCodeInfo, parse_agent_output
from autogemini.gemini_chat import ChatMessage, MessageRole

# --- All original helper imports remain unchanged ---
from plugin.util import online_py_executor
from plugin.util import mathworld


entity_name = "Chat"

# --- All path definitions and ContextManager class remain unchanged ---
context_temp_path = pathlib.Path(__file__).parent / "context_temp"
context_temp_path.mkdir(parents=True, exist_ok=True)
context_temp_file = context_temp_path / "context_temp.fjson"
profile_path = pathlib.Path(__file__).parent / "profiles"
profile_path.mkdir(parents=True, exist_ok=True)


# ... (ContextManager class and its methods like get_group_context, build_context, etc. are here, UNCHANGED)
def get_default_system_instruction():
    return example_prompt_package["Alice"].character


def get_gemini_key():
    return aibackend_package["apikey"].config.key_gemini()


class ContextManager:
    # ... (The entire ContextManager class is here, UNCHANGED)
    def __init__(self):
        self.group_context = {}
        self.private_context = {}

    def get_group_context(self, group_id):
        if str(group_id) not in self.group_context:
            self.group_context[str(group_id)] = {
                "context": message_codec_package["context"].ContextManager(context=[]),
                "stream_context": message_codec_package["context"].StreamContextManager(
                    context=[],
                    max_length=50,
                ),
                "ai_params": {
                    "system_instruction": get_default_system_instruction(),
                    "trigger": ["Alice"],
                },
            }
        return self.group_context[str(group_id)]

    def get_private_context(self, user_id):
        if str(user_id) not in self.private_context:
            self.private_context[str(user_id)] = {
                "context": message_codec_package[
                    "context"
                ].ContextManager(),  # 会话上下文，由于是私聊，所以无需流式上下文
                "ai_params": {
                    "system_instruction": get_default_system_instruction(),
                    "trigger": ["Alice"],
                },
            }
        return self.private_context[str(user_id)]

    def write_to_temporary_file(self):
        with open(context_temp_file, "w", encoding="utf-8") as f:
            group_context = {
                str(k): {
                    "context": v["context"].context,
                    "stream_context": (
                        v["stream_context"].context,
                        v["stream_context"].max_length,
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in self.group_context.items()
            }
            private_context = {
                str(k): {"context": v["context"].context, "ai_params": v["ai_params"]}
                for k, v in self.private_context.items()
            }
            f.write(
                fjson.encode(
                    {
                        "group_context": group_context,
                        "private_context": private_context,
                    },
                    multi_line=True,
                    indent=4,
                )
            )

    def read_from_temporary_file(self):
        with open(context_temp_file, "r", encoding="utf-8") as f:
            context = fjson.decode(f.read())
            self.group_context = {}
            self.private_context = {}
            self.group_context = {
                str(k): {
                    "context": message_codec_package["context"].ContextManager(
                        context=v["context"]
                    ),
                    "stream_context": message_codec_package[
                        "context"
                    ].StreamContextManager(
                        context=v["stream_context"][0],
                        max_length=v["stream_context"][1],
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in context["group_context"].items()
            }
            self.private_context = {
                str(k): {
                    "context": message_codec_package["context"].ContextManager(
                        context=v["context"]
                    ),
                    "ai_params": v["ai_params"],
                }
                for k, v in context["private_context"].items()
            }

    async def get_profile(self, user_id):
        group_profile_file = profile_path / f"user_{user_id}_profile.json"
        if not group_profile_file.exists():
            with open(group_profile_file, "w", encoding="utf-8") as f:
                f.write(fjson.encode({}))
        try:
            with open(group_profile_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log_func(
                "WARN",
                entity_name,
                f"Failed to get profile: {e}",
            )
            return None

    async def build_context(
        self,
        api,
        context,
        user_id,
        user_message_id,
        user_request,
        stream_context,
        group_id=None,
    ):
        _context = context.copy()

        async def build_header(
            user_id, user_message_id, user_sex, user_name, current=False
        ):
            return (
                ("# Current User(Talking to the assistant):" if current else "# User:")
                + f'`[CQ:at,qq={user_id}]`\n## msgid:`[CQ:reply,id={user_message_id}]`\n## Time:{time.asctime()}\n## User Sex:{user_sex}\n## User Name:"{user_name}"\n## User Request:\n'
            )

        profile = await self.get_profile(user_id)

        async def get_autosaves_file_informations():
            files = os.listdir(profile_path)
            result = []
            for file in files:
                file_path = profile_path / file
                file_size = os.path.getsize(file_path)
                file_modify_time = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(file_path))
                )
                file_create_time = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(file_path))
                )
                result.append(
                    {
                        "filename": file,
                        "size": file_size,
                        "modify_time": file_modify_time,
                        "create_time": file_create_time,
                    }
                )
            return result

        autosaves = await get_autosaves_file_informations()
        autosave_str = "<|start_header|>think<|end_header|>\n# here are my files saved in the past, I will use them as datebase to answer questions:\n"
        autosave_str += "filename | modify time\n --- | --- \n"
        for autosave in autosaves:
            autosave_str += f"{autosave['filename']} | {autosave['modify_time']}\n"
        autosave_str += "\n\n# Moreover, I should use `write_to_file` typesetting format to make my database fresh"

        _context.insert(
            0,
            {
                "role": "assistant",
                "content": autosave_str,
            },
        )

        if group_id:
            try:
                group_member_list = await api.get_member_list(group_id)
            except:
                group_member_list = []
            if len(group_member_list) <= 200:
                formatted_member_list = "```group member list\ncard | nickname | gender | qq\n --- | --- | --- | ---\n"
                for member in group_member_list:
                    formatted_member_list += f"{member['card']} | {member['nickname']} | {member['sex']} | {member['user_id']}\n"
                formatted_member_list += "```"
            elif len(group_member_list) <= 500:
                formatted_member_list = (
                    "```group member list\nnickname | qq\n --- | ---\n"
                )
                for member in group_member_list:
                    nickname = (
                        member["card"] if member["card"] != None else member["nickname"]
                    )
                    formatted_member_list += f"{nickname} | {member['user_id']}\n"
                formatted_member_list += "```"
            else:
                formatted_member_list = (
                    "```group member list\nmember count exceeds 500\n```"
                )

            _context.insert(
                0,
                {
                    "role": "assistant",
                    "content": f"<|start_header|>think<|end_header|># Group Member List:\n{formatted_member_list}",
                },
            )

        if stream_context:
            stream_context_str = ""
            for item in stream_context.get_message():
                stream_context_str += f"""# [{item['role']} [CQ:at,qq={item['user_id']}], name: {item['name']}]({item['time']}, msgid: [CQ:reply,id={item['message_id']}]):\n{item['content']}\n\n---\n\n"""
            _context.insert(
                0,
                {
                    "role": "user",
                    "content": f"# Group Message History Context (Multi-Users, Important):\n{stream_context_str}",
                },
            )

        user_info = await api.get_stranger_info(user_id)
        user_sex = user_info.get("sex", "unknown")
        user_name = user_info.get("nickname", "unknown")

        header_for_request = await build_header(
            user_id, user_message_id, user_sex, user_name
        )
        real_request = header_for_request + user_request  # Used for saving to history

        current_user_message_content = (
            f"# Current User Profile:\n{profile}\n"
            + await build_header(user_id, user_message_id, user_sex, user_name, True)
            + user_request
        )

        _context.append({"role": "user", "content": current_user_message_content})

        return _context, real_request


# --- NEW: AGENT HELPER FUNCTIONS ---


# --- Danbooru Logic (integrated from plugin) ---
class Danbooru:
    @staticmethod
    async def get_random_post(
        tags: Optional[str] = None, page: Optional[int] = None
    ) -> Optional[dict]:
        """Fetches a random Danbooru post, returning its data dictionary."""
        # This is the exact code from your plugin file.
        # Note: I've made it a @staticmethod for easier calling without an instance.
        base_url = "https://danbooru.donmai.us/posts"

        if page is None:
            page = random.randint(1, 100)

        params = {"page": page}
        if tags:
            # Danbooru API recommends a limit of 2 tags for unauthenticated users for speed.
            # We will enforce this in the tool's prompt, but the function can handle more.
            params["tags"] = tags

        log_func("INFO", "DanbooruTool", f"Requesting Danbooru with params: {params}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(base_url, params=params, timeout=60) as response:
                    if response.status != 200:
                        log_func(
                            "ERROR",
                            "DanbooruTool",
                            f"Failed to get post list: {response.status}",
                        )
                        return None

                    soup = bs4.BeautifulSoup(await response.text(), "html.parser")
                    posts = soup.select("article.post-preview")
                    if not posts:
                        return None

                    post = random.choice(posts)
                    img_url = post.get("data-file-url")
                    large_img_url = post.get("data-large-file-url")

                    # Prefer larger image if available, fallback to file_url
                    final_image_url = large_img_url or img_url

                    if not final_image_url:
                        return None

                    return {
                        "tags": post.get("data-tags"),
                        "img_url": final_image_url,
                        "post_id": post.get("data-id"),
                    }
            except Exception as e:
                log_func(
                    "ERROR", "DanbooruTool", f"Exception during Danbooru fetch: {e}"
                )
                return None


def get_agent_tool_codes() -> List[ToolCodeInfo]:
    """Defines the tools available to the agent in the required format."""
    return [
        ToolCodeInfo(
            name="search_on_web",
            description="Searches the web for up-to-date or unknown information. Use this if you cannot answer from your own knowledge.",
            detail="Performs a web search using the Bing engine and returns a summary of the results.",
            args={"query": "A clear and concise search query string."},
        ),
        ToolCodeInfo(
            name="get_webpage_content",
            description="Retrieves the full text content from a specific webpage URL.",
            detail="Given a URL, this tool will open it and return all readable text in Markdown format.",
            args={
                "url": "The complete and valid URL of the webpage (e.g., 'https://www.example.com')."
            },
        ),
        ToolCodeInfo(
            name="execute_python",
            description="Executes Python code in a sandboxed environment for calculations, data manipulation, or algorithmic tasks. Cannot access the network or local files.",
            detail="The final line of the code should be an expression or a `print()` call to produce an output.",
            args={"code": "A string containing valid Python code to be executed."},
        ),
        ToolCodeInfo(
            name="compute_with_wolfram",
            description="Solves complex mathematical problems, answers scientific questions, and provides structured data using the Wolfram Alpha engine.",
            detail="Ideal for calculus, algebra, chemistry, physics, and knowledge-based queries.",
            args={
                "expression": "The mathematical expression or natural language query for Wolfram Alpha."
            },
        ),
        ToolCodeInfo(
            name="read_from_file",
            description="Reads the content of one or more files that you have previously saved.",
            detail="You can provide multiple filenames separated by a pipe character ('|').",
            args={
                "filenames": "The name of the file(s) to read, e.g., 'notes.txt' or 'plan.md|data.json'."
            },
        ),
        ToolCodeInfo(
            name="write_to_file",
            description="Writes or overwrites content to a specified file in your personal storage.",
            detail="This tool is useful for saving your thought processes, plans, code snippets, or long-term information that the user asks you to remember. If the file already exists, it will be completely replaced with the new content.",
            args={
                "filename": "The name of the file to write to, e.g., 'my_notes.txt' or 'code_snippet.py'.",
                "content": "The text content to write into the file.",
            },
        ),
        ToolCodeInfo(
            name="search_on_mathworld",
            description="Searches Wolfram MathWorld for detailed definitions, theorems, and formulas related to a specific mathematical concept.",
            detail="This is a specialized tool for deep mathematical research.",
            args={
                "query": "The mathematical term or concept to look up (e.g., 'Eigenvalue' or 'Riemann Hypothesis')."
            },
        ),
        ToolCodeInfo(
            name="search_on_danbooru",
            description="Searches for a random SFW (safe-for-work) or NSFW (not-safe-for-work) anime-style image on the Danbooru image board. Use this when the user asks for a 'random picture', 'anime image', or something similar.",
            detail="You can provide tags to narrow the search. **IMPORTANT: You can only use a maximum of TWO (2) tags.** Tags with multiple words must be joined by an underscore (e.g., 'blue_hair'). The tool returns a direct URL to the image.",
            args={
                "tags": "A string containing one or two tags, separated by a space. Example: '1girl blue_hair'. Leave empty for a completely random image."
            },
        ),
    ]


async def create_agent_api_handler() -> DefaultApi:
    """Creates the API handler that maps tool names to their actual implementation."""

    async def api_handler(method_name: str, *args, **kwargs) -> Any:
        log_func(
            "INFO",
            entity_name,
            f"Agent Tool Call: {method_name} with args: {args}, kwargs: {kwargs}",
        )

        # Prefer kwargs, but fallback to args for simpler tool definitions
        first_arg = next(iter(kwargs.values()), None) or (args[0] if args else None)
        if first_arg is None:
            return f"[Error] Tool '{method_name}' was called without any arguments."

        try:
            if method_name == "search_on_web":
                return await document_renderer_package["renderer"].web_search(
                    await plugin_context.bot_entity.browser.get_browser(),
                    first_arg,
                    20,
                    "Bing",
                )
            elif method_name == "get_webpage_content":
                return await document_renderer_package["renderer"].get_webpage(
                    await plugin_context.bot_entity.browser.get_browser(),
                    first_arg,
                    only_text=True,
                    max_token=4096,
                )
            elif method_name == "execute_python":
                return await online_py_executor.execute_python_code(first_arg)
            elif method_name == "compute_with_wolfram":
                return await document_renderer_package[
                    "renderer"
                ].wolfram_alpha.wolfram_alpha_compute_without_image(first_arg)
            elif method_name == "read_from_file":
                files = first_arg.split("|")
                result_dict = {}
                for file in files:
                    file_name = file.strip()
                    try:
                        with open(profile_path / file_name, "r", encoding="utf-8") as f:
                            result_dict[file_name] = f.read()
                    except Exception as e:
                        result_dict[file_name] = (
                            f"[System] Failed to read file '{file_name}': {e}"
                        )
                return result_dict
            elif method_name == "write_to_file":
                filename = kwargs.get("filename")
                content = kwargs.get("content")
                if (
                    not filename or content is None
                ):  # content可以是空字符串，所以要判断None
                    return "[Error] `write_to_file` tool requires both 'filename' and 'content' arguments."

                # 使用之前定义好的 profile_path
                file_path = profile_path / filename
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                log_func("INFO", entity_name, f"Successfully wrote to file: {filename}")
                return f"[Success] Content has been saved to '{filename}'."
            elif method_name == "search_on_mathworld":
                result = await mathworld.get_content_from_results(first_arg, n=3)
                return result or "No results found on MathWorld."
            elif method_name == "search_on_danbooru":
                # The 'first_arg' will be the tags string, or None
                tags = first_arg
                log_func(
                    "INFO",
                    entity_name,
                    f"Agent is searching Danbooru with tags: {tags}",
                )

                # Call the Danbooru logic we added to this file
                post_data = await Danbooru.get_random_post(tags=tags)

                if post_data and post_data.get("img_url"):
                    # Success! Return JUST the URL to the agent.
                    return post_data["img_url"]
                else:
                    # Provide a helpful error message back to the agent
                    return f"[Error] Could not find an image on Danbooru for the tags: '{tags}'. Please try different tags or no tags at all."
            else:
                return f"[Error] Unknown tool called: {method_name}"
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Error executing tool '{method_name}': {traceback.format_exc()}",
            )
            return f"[Error] An exception occurred while executing tool '{method_name}': {e}"

    return DefaultApi(api_handler)


def convert_history_to_chat_messages(history: List[dict]) -> List[ChatMessage]:
    """Converts the plugin's dictionary-based history to the agent's ChatMessage format."""
    chat_messages: List[ChatMessage] = []
    for item in history:
        role = None
        if item.get("role") == "user":
            role = MessageRole.USER
        elif item.get("role") == "assistant":
            role = (
                MessageRole.ASSISTANT
            )  # The agent's own responses are tagged as 'model'

        if role and "content" in item:
            chat_messages.append(ChatMessage(role=role, content=str(item["content"])))

    return chat_messages


# --- END AGENT HELPER FUNCTIONS ---


CUSTOM_TAGS_PROMPT = """
Your final response must be formatted using ONLY the tags listed below.
This allows your response to be displayed correctly and for special actions to be executed.

---
### **Part 1: Standard HTML Formatting Tags**
Use these for structuring your text response.

- `<p>...</p>`: For standard paragraphs.
- `<br>`: For line breaks within paragraphs.
- `<h1>, <h2>, <h3>`: For section headings.
- `<strong>, <b>`: For strong emphasis.
- `<em>, <i>`: For general emphasis.
- `<ul>, <ol>, <li>`: For lists.
- `<code>, <pre>`: For code blocks.
- `<br>`: For a line break.
- `<a href="...">...</a>`: For hyperlinks.

---
### **Part 2: Special Action Tags**
Use these tags to perform specific actions. Do NOT use them for simple text formatting.

**1. Text-to-Speech:**
   - **Tag:** `<tts emotion="...">...</tts>`
   - **Purpose:** Converts the enclosed text into a voice message.
   - **Attributes:** `emotion` (optional) - can be "happy", "sad", "excited", etc., to influence the voice tone.
   - **Example:** `<tts emotion="excited">主人，我算出来啦！</tts>`

**2. AI Painting:**
   - **Tag:** `<paint style="..." orientation="...">...</paint>`
   - **Purpose:** Generates an image based on the enclosed English prompt.
   - **Attributes:**
     - `style`: "anime" (default) or "photo".
     - `orientation`: "wide" (default) or "tall".
   - **Example:** `<paint style="anime" orientation="tall">1girl, white hair, cat ears, looking at viewer</paint>`

**3. Ban a User (Group Admin Only):**
   - **Tag:** `<ban user_id="..." minutes="...">...</ban>`
   - **Purpose:** Bans a user from the group for a specified duration.
   - **Attributes:**
     - `user_id`: The QQ number of the user to ban.
     - `minutes`: The duration of the ban (1-10 minutes).
   - **Example:** `<ban user_id="12345678" minutes="5">This user was spamming.</ban>`

**4. Wolfram|Alpha Calculation Display:**
   - **Tag:** `<wolfram>...</wolfram>`
   - **Purpose:** Computes the enclosed query using Wolfram|Alpha and displays the result as an image.
   - **Example:** `<wolfram>integrate x^2 dx from 0 to 1</wolfram>`

**5. Markdown to Image Rendering:**
   - **Tag:** `<markdown-render>...</markdown-render>`
   - **Purpose:** Renders the enclosed Markdown content as an image. Use this for complex tables, formulas, or layouts that standard HTML can't handle.
   - **Example:** `<markdown-render>| Header 1 | Header 2 |\n|---|---|\n| Cell 1 | Cell 2 |</markdown-render>`

**6. Display Image from URL:**
   - **Tag:** `<image src="..." />`
   - **Purpose:** Downloads an image from a public URL and displays it directly in the chat.
   - **Attributes:** `src` - The full, direct URL to the image file (e.g., .png, .jpg, .gif).
   - **Example:** `<image src="https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png" />`

---
### **Final Instruction**
Your entire final response must be composed using a sequence of the tags described above.

# Remember: ALL your responses must be output after `<|start_header|>response<|end_header|>` BLOCK
"""


def get_typeset_handler(api, browser, template):
    async def handle_shut_up(x: dict, group_id: int, **kwargs) -> tuple[str, str]:
        user = x["user_id"]
        time = x["minutes"]
        time = 10 if time > 10 else (time if time > 0 else 1)
        await api.set_group_ban(group_id, user, time * 60)
        return f" 已禁言[CQ:at,qq={user}]{time}分钟 "

    async def handle_tts(x: dict, **kwargs) -> str:
        text = x["text"]
        emotion = x.get("emotion", "")
        log_func("INFO", entity_name, f"Text to speech: {text}")
        result = await aibackend_package["tts"].text_to_speech_cosyvoice(text, emotion)
        result = base64.b64encode(result).decode()
        return f"[CQ:record,file=base64://{result}]"

    async def handle_wolfram(x: dict, markdown: bool, **kwargs) -> str:
        cal = x["script"]
        result = await document_renderer_package[
            "renderer"
        ].wolfram_alpha.wolfram_alpha_compute(cal, image_only=True)

        if markdown:
            return (
                "\n"
                + await document_renderer_package[
                    "renderer"
                ].wolfram_alpha.format_to_HTML(result)
                + "\n"
            )
        formatted = (
            "\n"
            + await document_renderer_package["renderer"].wolfram_alpha.format_to_CQ(
                result
            )
            + "\n"
        )
        return formatted if formatted is not None else "Failed to calculate"

    async def handle_markdown_render(
        x: dict, _FUNCTION_HANDLERS=None, markdown=False, **kwargs
    ) -> str:
        try:
            markdown_str = x["content"]
            markdown_str = await template.process_chatbot_typeset(
                markdown_str,
                FUNCTION_HANDLERS=_FUNCTION_HANDLERS,
                markdown=True,
                _FUNCTION_HANDLERS=_FUNCTION_HANDLERS,
                **kwargs,
            )
            result = await document_renderer_package["renderer"].MarkdownRenderer(
                browser
            )(markdown_str)
            if result is None:
                return "Failed to render Markdown"
            return (
                f"[CQ:image,file=base64://{base64.b64encode(result).decode()},id=40000]"
            )
        except Exception as e:
            log_func("ERROR", entity_name, f"Failed to render markdown: {e}")
            return markdown_str

    async def handle_graphic_art(x: dict, **kwargs) -> str:
        is_vertical = x.get("vertical", False)
        style = x.get("style", "anime")
        prompt = x["prompt"]
        size = (
            aibackend_package["aipaint"].ImageSize.TALL
            if is_vertical
            else aibackend_package["aipaint"].ImageSize.WIDE
        )
        style = (
            aibackend_package["aipaint"].ImageStyle.ANIME
            if style == "anime"
            else aibackend_package["aipaint"].ImageStyle.PHOTO
        )
        result = await aibackend_package["aipaint"].generate_image(
            prompt, size, style, aibackend_package["aipaint"].APILevel.FREE
        )
        return f"[CQ:image,file=base64://{base64.b64encode(result).decode()}]"

    async def handle_image_from_url(tag: BeautifulSoup) -> str:
        url = tag.get("src")
        if not url or not url.startswith(("http://", "https://")):
            return "[图片错误: 无效的URL]"

        log_func("INFO", entity_name, f"Processing image URL: {url}")
        try:
            async with aiohttp.ClientSession() as session:
                # 1. 先用 HEAD 请求检查 URL 和内容类型，避免下载大文件
                async with session.head(url, timeout=10) as response:
                    if response.status != 200:
                        return f"[图片错误: URL无法访问，状态码 {response.status}]"

                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        return f"[图片错误: URL指向的不是一个图片文件 ({content_type})]"

                # 2. 检查通过后，再用 GET 请求下载图片内容
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        encoded_data = base64.b64encode(image_data).decode("utf-8")
                        return f"[CQ:image,file=base64://{encoded_data}]"
                    else:
                        return f"[图片错误: 下载失败，状态码 {response.status}]"

        except asyncio.TimeoutError:
            return "[图片错误: 访问URL超时]"
        except Exception as e:
            log_func("ERROR", entity_name, f"Error processing image URL {url}: {e}")
            return f"[图片错误: 处理时发生未知异常]"

    return {
        "DocumentRender": handle_markdown_render,
        "shut_up": handle_shut_up,
        "text_to_speech": handle_tts,
        "display_wolframalpha": handle_wolfram,
        "graphic_art_in_English": handle_graphic_art,
        "image_from_url": handle_image_from_url,
    }


async def handle_agent_output(
    html_output: str,
    api: Any,  # Pass the onebot api instance
    browser: Any,  # Pass the browser instance
    group_id: int,  # Pass the group_id for context
) -> str:
    """
    Parses the agent's HTML output, executes special action tags,
    and returns a string ready to be sent to the message API.
    """
    if not BeautifulSoup:
        log_func("ERROR", "Chat", "BeautifulSoup is not installed, returning raw HTML.")
        return html_output

    soup = BeautifulSoup(html_output, "lxml")

    # Get the legacy handler functions, which we will reuse
    legacy_handlers = get_typeset_handler(api, browser, template)

    # Process each custom tag type

    # <tts>
    for tag in soup.find_all("tts"):
        result_cq = await legacy_handlers["text_to_speech"](
            {"text": tag.get_text(strip=True), "emotion": tag.get("emotion", "")}
        )
        tag.replace_with(result_cq)  # Replace the tag with the [CQ:record] code

    # <paint>
    for tag in soup.find_all("paint"):
        result_cq = await legacy_handlers["graphic_art_in_English"](
            {
                "prompt": tag.get_text(strip=True),
                "style": tag.get("style", "anime"),
                "vertical": tag.get("orientation") == "tall",
            }
        )
        tag.replace_with(result_cq)  # Replace with [CQ:image]

    # <ban>
    for tag in soup.find_all("ban"):
        # The text inside the tag is the ban reason, which can be part of the confirmation message
        reason = tag.get_text(strip=True)
        confirmation_text, _ = await legacy_handlers["shut_up"](
            {"user_id": tag.get("user_id"), "minutes": int(tag.get("minutes", 1))},
            group_id=group_id,
        )
        tag.replace_with(f"{confirmation_text} (Reason: {reason})")

    # <wolfram>
    for tag in soup.find_all("wolfram"):
        result_cq = await legacy_handlers["display_wolframalpha"](
            {"script": tag.get_text(strip=True)}, markdown=False
        )  # Get CQ code, not HTML
        tag.replace_with(result_cq)

    # <markdown-render>
    for tag in soup.find_all("markdown-render"):
        # We need to be careful here to avoid infinite recursion if markdown-render itself contains action tags
        # The content should be plain markdown.
        result_cq = await legacy_handlers["DocumentRender"](
            {"content": tag.get_text()},  # Don't strip, preserve whitespace
            _FUNCTION_HANDLERS=legacy_handlers,
            markdown=False,
        )
        tag.replace_with(result_cq)

    # <image src="...">
    for tag in soup.find_all("image"):
        result_cq = await legacy_handlers["image_from_url"](tag)
        tag.replace_with(result_cq)

    final_text = soup.get_text(separator="", strip=True)

    return final_text


class Plugin:
    context_manager = None
    lock = Lock()
    rate_limiter = plugin_context.RateLimiter(300, 400)

    # All static methods (create, help, description, destroy, etc.) remain UNCHANGED.
    @staticmethod
    def create():
        Plugin.context_manager = ContextManager()
        try:
            Plugin.context_manager.read_from_temporary_file()
            log_func(
                "INFO",
                entity_name,
                "Context loaded from temporary file successfully!",
            )
        except Exception as e:
            log_func(
                "WARN",
                entity_name,
                "Failed to load context from temporary file, creating new context...",
            )
            Plugin.context_manager = ContextManager()

        log_func(
            "INFO",
            entity_name,
            r"""

AI Chat Plugin is initialized!
""",
        )

    @staticmethod
    def help():
        return r"""
AI Chat Plugin
================
This plugin is used to chat with AI.

Commands:
- `#context --save_all`: Save all context to temporary file.
- `#context --load_all`: Load all context from temporary file.
- `#sudo --set_trigger trigger1 trigger2 ... `: Set trigger for AI.
- `#sudo --set_instruction "system instruction"`: Set instruction for AI. Empty to reset to default.
""".strip()

    @staticmethod
    def description():
        return r"""
AI Chat Plugin
================
This plugin is used to chat with AI.
Powered by ✨Gemini-Flash-2.0 via AutoGemini Agent
""".strip()

    @staticmethod
    def destroy():
        try:
            Plugin.context_manager.write_to_temporary_file()
            log_func(
                "INFO",
                entity_name,
                "Context saved to temporary file successfully!",
            )
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to save context to temporary file! {traceback.format_exc()}",
            )

    @staticmethod
    def before_reload():
        with Plugin.lock:
            log_func("INFO", entity_name, "Writing context to temporary file...")
            Plugin.context_manager.write_to_temporary_file()

    @staticmethod
    def after_reload():
        with Plugin.lock:
            log_func("INFO", entity_name, "Reading context from temporary file...")
            Plugin.context_manager = ContextManager()
            Plugin.context_manager.read_from_temporary_file()

    @staticmethod
    def _test_if_being_at(message, bot_qq):
        for x in message:
            if x["type"] == "at" and x["data"]["qq"] == str(bot_qq):
                return True
        return False

    @staticmethod
    async def process_sudo_command(message, group_context, message_sender_func):
        sender = message["sender"]
        command = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image_tag(
            message["message"], message["self_id"]
        )

        command = command.strip()
        if not command.startswith(plugin_context.bot_entity.sudo_command_trigger):
            return
        if not sender["user_id"] in plugin_context.bot_entity.admins:
            await message_sender_func("Permission denied.")
            log_func(
                "ERROR",
                "Bot",
                "Permission denied for sudo command:",
                command,
                "because",
                sender["user_id"],
                "is not in the admin list.",
            )
            raise plugin_context.SkipFollow()
        command = command.replace(
            plugin_context.bot_entity.sudo_command_trigger, "", 1
        ).strip()
        log_func("INFO", "Bot", "Received sudo command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            if "set_trigger" in command_json:
                group_context["ai_params"]["trigger"] = command_json["set_trigger"]
                await message_sender_func("Set trigger successfully.")
                raise plugin_context.SkipFollow()
            if "set_instruction" in command_json:
                if command_json["set_instruction"] == []:
                    group_context["ai_params"][
                        "system_instruction"
                    ] = get_default_system_instruction()
                else:
                    group_context["ai_params"]["system_instruction"] = command_json[
                        "set_instruction"
                    ][0]
                await message_sender_func("Set instruction successfully.")
                raise plugin_context.SkipFollow()
        except plugin_context.SkipFollow:
            raise plugin_context.SkipFollow()
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)

    @staticmethod
    async def process_context_command(message, message_sender_func, context):
        command = await message_codec_package[
            "codec"
        ].encode_message_to_CQ_without_At_self_and_Image_tag(
            message["message"], message["self_id"]
        )

        command = command.strip()
        trigger = "#context "
        if not command.startswith(trigger):
            return

        command = command.replace(trigger, "", 1).strip()
        log_func("INFO", "Bot", "Received context command:", command)

        try:
            command_json = fjson.decode(command)  # 解析json
        except Exception as e:
            log_func("ERROR", "Bot", "Failed to parse command:", e)
            await message_sender_func("Failed to parse command.")
            raise Exception("#sudo command is invalid: " + command)
        try:
            if "save_all" in command_json:
                Plugin.context_manager.write_to_temporary_file()
                await message_sender_func("Save context successfully.")
            if "load_all" in command_json:
                Plugin.context_manager.read_from_temporary_file()
                await message_sender_func("Load context successfully.")
            if "clear" in command_json:
                context["context"].clear()
                await message_sender_func("Clear context successfully.")
            if "withdraw" in command_json:
                context["context"].withdraw()
                await message_sender_func("Withdraw context successfully.")

        except Exception as e:
            log_func("ERROR", "Bot", "Failed to execute command:", e)
            await message_sender_func(f"Failed to execute command.\n{e}")
            raise Exception("#sudo command is invalid: " + command)
        raise plugin_context.SkipFollow()

    # --- CORE LOGIC: on_group_message is completely refactored ---
    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)

        async def timeout_callback():
            await api.send_group_message(message["group_id"], "AI Chat Plugin Timeout!")

        @plugin_context.timeout(600, timeout_callback=timeout_callback)
        async def handler():
            group_id = message["group_id"]
            group_context = Plugin.context_manager.get_group_context(group_id)

            await Plugin.process_sudo_command(
                message, group_context, lambda x: api.send_group_message(group_id, x)
            )
            await Plugin.process_context_command(
                message, lambda x: api.send_group_message(group_id, x), group_context
            )

            message_str = await message_codec_package[
                "codec"
            ].encode_message_to_CQ_without_At_self_and_Image_tag(
                message["message"], message["self_id"]
            )

            def check_trigger(message):
                for trigger in group_context["ai_params"]["trigger"]:
                    if trigger in message:
                        return True
                return False

            @plugin_context.async_ratelimit(
                limiter=Plugin.rate_limiter,
                on_limit_exceeded=lambda wait_time: None,
                throw_on_limit=True,
            )
            async def limited_handler():
                pass

            if Plugin._test_if_being_at(
                message["message"], message["self_id"]
            ) or check_trigger(message_str):
                await limited_handler()

                log_func(
                    "INFO", entity_name, f"Triggered by message from group {group_id}."
                )
                message_id = await api.send_group_message(
                    group_id, "我正在思考如何回复你 (Agent模式)..."
                )

                user_message_for_agent = await message_codec_package[
                    "codec"
                ].encode_message_to_CQ_without_At_self_and_Image(
                    message["message"], message["self_id"]
                )

                # --- AGENT INTEGRATION BLOCK ---

                # 1. Build the full context using the existing, powerful build_context method.
                full_context_list, real_request_for_history = (
                    await Plugin.context_manager.build_context(
                        api,
                        group_context["context"].get_message(),
                        message["user_id"],
                        message["message_id"],
                        user_message_for_agent,
                        group_context["stream_context"],
                        group_id,
                    )
                )

                # 2. The last message in the list is the current user's prompt. Separate it.
                current_user_message_dict = full_context_list.pop()
                current_user_prompt = current_user_message_dict.get("content", "")

                # 3. Convert the rest of the list into the agent's history format.
                agent_history = convert_history_to_chat_messages(full_context_list)

                # 4. Prepare the agent by creating its tools and API handler.
                agent_api_handler = await create_agent_api_handler()
                agent_tool_codes = get_agent_tool_codes()

                gemini_api_key = get_gemini_key()
                if not gemini_api_key:
                    await api.withdraw_message(message_id)
                    await api.send_group_message(
                        group_id, "错误：机器人未配置Gemini API Key。"
                    )
                    log_func(
                        "ERROR",
                        entity_name,
                        "Gemini API Key not found in bot_entity config.",
                    )
                    return

                # 5. Create a new agent processor for this specific request.
                processor = create_cot_processor(
                    api_key=gemini_api_key,
                    default_api=agent_api_handler,
                    tool_codes=agent_tool_codes,
                    character_description=group_context["ai_params"][
                        "system_instruction"
                    ],
                    respond_tags_description=CUSTOM_TAGS_PROMPT,
                )

                # 6. Load the conversation history into the agent.
                processor.load_history(agent_history)

                # 7. Define a simple callback for debugging the agent's internal steps.
                def stream_callback(chunk: Any, msg_type: CallbackMsgType):
                    log_func("DEBUG", f"Agent-{msg_type.name}", str(chunk))

                # 8. Run the agent's processing loop.
                try:
                    log_func("INFO", entity_name, "Starting agent processing...")
                    final_response = await processor.process_conversation(
                        current_user_prompt,
                        callback=stream_callback,
                        tool_code_timeout=90.0,
                    )

                    # 9. Process and send the final response.
                    await api.withdraw_message(message_id)

                    agent_output = parse_agent_output(final_response)
                    ai_output = "No response"
                    for item in agent_output:
                        if item.type == "response":
                            ai_output = item.content

                    parsed_output = await handle_agent_output(
                        ai_output,
                        api,
                        await plugin_context.bot_entity.browser.get_browser(),
                        group_id,
                    )

                    await api.send_group_message_separate_audio(
                        group_id,
                        await message_codec_package["codec"].decode_CQ_to_message(
                            parsed_output
                        ),
                    )

                    # 10. Save the complete interaction to context manager.
                    group_context["context"].push_message(
                        {
                            "role": "user",
                            "content": real_request_for_history,
                        }
                    )
                    group_context["context"].push_message(
                        {
                            "role": "assistant",
                            "content": final_response,
                        }
                    )
                except Exception as e:
                    await api.withdraw_message(message_id)
                    error_msg = f"Agent在处理时发生错误: {e}"
                    log_func(
                        "ERROR", entity_name, f"{error_msg}\n{traceback.format_exc()}"
                    )
                    await api.send_group_message(group_id, error_msg)

                # --- END AGENT INTEGRATION BLOCK ---

            else:
                # This part for non-triggered messages remains the same
                group_context["stream_context"].push_message(
                    {
                        "role": "user",
                        "name": message["sender"]["nickname"],
                        "user_id": message["user_id"],
                        "time": time.asctime(),
                        "message_id": message["message_id"],
                        "content": message_str,
                    }
                )

        try:
            await handler()
        except plugin_context.SkipFollow:
            raise plugin_context.SkipFollow()
        except plugin_context.Skip:
            raise plugin_context.Skip()
        except plugin_context.RateLimitedError as e:
            await api.send_group_message(message["group_id"], str(e))
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle group message: {traceback.format_exc()}",
            )
            await api.send_group_message(
                message["group_id"], "AI聊天插件处理消息失败！\n" + str(e)
            )

    # on_poke remains unchanged. It cleverly reuses on_group_message.
    @staticmethod
    async def on_poke(ws, message):
        api = onebot_package["api"].OneBotAPI(ws, plugin_context.echo_pool)
        group_id = message["group_id"]
        fake_message = {
            "message_id": message.get("message_id", "0"),
            "group_id": group_id,
            "user_id": message.get("user_id", "0"),
            "self_id": message.get("self_id", "0"),
            "sender": message.get(
                "sender",
                {"nickname": "unknown", "user_id": message.get("user_id", "0")},
            ),
            "message": [
                {"type": "text", "data": {"text": "[戳一戳]"}},
                {"type": "at", "data": {"qq": str(message.get("target_id", "0"))}},
            ],
        }
        try:
            await Plugin.on_group_message(ws, fake_message)
        except Exception as e:
            log_func(
                "ERROR",
                entity_name,
                f"Failed to handle poke as group message: {traceback.format_exc()}",
            )
            await api.send_group_message(group_id, "处理戳一戳时出错！")
