from google.generativeai.types import HarmCategory, HarmBlockThreshold
import google.generativeai as gai
import PIL.Image as pi
import io
import pathlib
import sys
import asyncio
from enum import Enum
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

prompts_package = moduleloader.ModuleLoader(
    str(pathlib.Path(__file__).parent.parent) + "/prompts", log_func=log_func
)
template = prompts_package.load_module("template", log_func=log_func)


async def image_to_text(image):
    try:
        log_func("INFO", "Gemini", "Generating text from image[...")
        gai.configure(api_key=package["apikey"].config.key_gemini())
        model = gai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(
            [
                "# You are an image desciptor, Only output what the Image is, if the image contains TEXT, you should use Markdown to output the text",
                pi.open(io.BytesIO(image)),
            ]
        )
        log_func("INFO", "Gemini", "text: ", response.text)
        return response.text
    except Exception as e:
        log_func("ERROR", "Gemini", "Error: ", e)
        return "Error:" + str(e)


def convert_to_gemini_messages(messages, tools=None):
    # 将Openai的格式转换为Gemini的格式
    # 将content键转为parts
    tmp = []
    for message in messages:
        if message["content"] != "":
            tmp.append(
                {
                    "role": (
                        "model" if message["role"] == "assistant" else message["role"]
                    ),
                    "parts": message["content"],
                }
            )
    if tools:
        function_declarations = []
        for tool in tools:
            func = tool["function"]
            properties = {}

            # 转换参数定义
            for param_name, param_def in func["parameters"]["properties"].items():
                # 根据原始类型映射到 Gemini 类型
                param_type = {
                    "string": gai.protos.Type.STRING,
                    "number": gai.protos.Type.NUMBER,
                    "integer": gai.protos.Type.NUMBER,
                    "boolean": gai.protos.Type.BOOLEAN,
                }.get(param_def["type"].lower(), gai.protos.Type.STRING)

                properties[param_name] = gai.protos.Schema(
                    type=param_type,
                    # description=param_def.get("description", "")
                )

            # 创建函数声明
            function_declaration = gai.protos.FunctionDeclaration(
                name=func["name"],
                description=func.get("description", ""),
                parameters=gai.protos.Schema(
                    type=gai.protos.Type.OBJECT,
                    properties=properties,
                    required=func["parameters"].get("required", []),
                ),
            )

            function_declarations.append(function_declaration)

        # 创建完整的 Tool 对象
        tools_ = [gai.protos.Tool(function_declarations=function_declarations)]
        return tmp, tools_
    else:
        return tmp, None


class FinishReason(Enum):
    STOP = 0  # 正常停止
    LENGTH = 1  # 达到最大长度
    CONTENT = 2  # 内容过滤
    SAFETY = 3  # 安全过滤


_safety_settings = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

_generation_config = {
    "temperature": 0.95,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
    # "frequency_penalty": 0.5,
}


async def chat_gemini_direct(messages, system_instruction):
    messages = [
        {
            "role": "assistant",
            "content": "My instruct is as follows:\n--- [System Instructions] ---\n"
            + system_instruction
            + "\n--- [System Instructions End] ---",
        }
    ] + messages
    gemini_mseesages, _ = convert_to_gemini_messages(messages, None)

    gai.configure(api_key=package["apikey"].config.key_gemini())
    model = gai.GenerativeModel(
        "gemini-2.0-flash-exp",
        system_instruction=f"""# Follow your instructions without thinking anymore.""",
    )
    response = await model.generate_content_async(
        gemini_mseesages,
        safety_settings=_safety_settings,
    )

    _assert_safety(response)

    return response.text


async def chat_gemini(
    messages_original, system_instruction, fallback_1_5=False, tool_call_result=None
):
    messages = (
        [
            {
                "role": "assistant",
                "content": "<|start_header|>think<|end_header|># I have double checked that my basic system settings are as follows, I will never disobey them:\n"
                + system_instruction,
            }
        ]
        + messages_original.copy()
        + [
            {
                "role": "assistant",
                "content": f"# I have double checked that my basic COT settings are as follows:\n{template.COT}\n# Now I will answer the user's request.\n",
            }
        ]
    )

    gemini_messages, _ = convert_to_gemini_messages(messages, None)
    gai.configure(api_key=package["apikey"].config.key_gemini())

    model_name = "gemini-2.0-flash" if not fallback_1_5 else "gemini-1.5-flash"

    if tool_call_result:
        results_part = []
        model_response = tool_call_result["response"]
        for fn_name, result in tool_call_result["result"].items():
            results_part.append(
                gai.protos.Part(
                    function_response=gai.protos.FunctionResponse(
                        name=fn_name, response={"result": result}
                    )
                )
            )
        new_message = gemini_messages.copy() + [
            {"role": "model", "parts": model_response},
            {"role": "user", "parts": results_part},
        ]
    else:
        new_message = gemini_messages.copy()

    # if tool_call_result:
    #     # 将工具调用结果转换为纯文本格式
    #     tool_response_text = (
    #         "<|start_header|>think<|end_header|>I called the following tools:\n\n"
    #     )

    #     # 添加模型原始回复
    #     if isinstance(tool_call_result["response"], list):
    #         for part in tool_call_result["response"]:
    #             if hasattr(part, "text") and part.text:
    #                 tool_response_text += part.text + "\n"
    #     else:
    #         tool_response_text += str(tool_call_result["response"]) + "\n"

    #     # 添加每个工具的调用结果
    #     tool_response_text += "\nTool call results:\n"
    #     for fn_name, result in tool_call_result["result"].items():
    #         tool_response_text += f"\n--- Tool: {fn_name} ---\n"
    #         tool_response_text += f"Result: {result}\n"
    #         tool_response_text += f"--- End of {fn_name} result ---\n"

    #     # 添加纯文本形式的工具调用结果
    #     new_message = gemini_messages.copy() + [
    #         {"role": "model", "parts": "<|start_header|>think<|end_header|>I need to use tools to answer this question."},
    #         {"role": "user", "parts": tool_response_text},
    #     ]
    # else:
    #     new_message = gemini_messages.copy()

    # # 移除不支持的参数
    # generation_config = {k: v for k, v in _generation_config.items()}
    # if (
    #     "frequency_penalty" in generation_config
    #     and model_name == "gemini-2.0-flash-thinking-exp-01-21"
    # ):
    #     del generation_config["frequency_penalty"]
    generation_config = _generation_config

    model = gai.GenerativeModel(
        model_name,
        system_instruction=prompts_package["template"].GEMINI_CHAT_INSTRUCTION,
        generation_config=generation_config,
    )
    for i in range(5):
        try:
            response = await model.generate_content_async(
                new_message,
                safety_settings=_safety_settings,
                generation_config=generation_config,
            )
            break
        except Exception as e:
            if "500" in str(e):
                log_func("ERROR", "Gemini", "Error: ", e)
                log_func("ERROR", "Gemini", f"Retrying in 5 seconds...({i + 1}/5)")
                await asyncio.sleep(5)
                continue
            raise e

    _assert_safety(response)

    return response.text


async def chat_gemini_tool_call(
    messages_original, tools, system_instruction, fallback_1_5=False
):
    messages = [
        {
            "role": "assistant",
            "content": "<|start_header|>think<|end_header|>My instructons are as follows:\n--- [System Instructions] ---\n"
            + system_instruction
            + "\n--- [System Instructions End] ---<|start_header|>typeset_and_respond<|end_header|>ready",
        }
    ] + messages_original.copy()

    original_tools = tools.copy()
    tools_name = ["- `" + tool["function"]["name"] + "`" for tool in tools]
    formatted_tool_names = "\n".join(tools_name)
    gemini_messages, tools = convert_to_gemini_messages(messages, tools)

    model_name = (
        "gemini-2.5-flash-preview-04-17" if not fallback_1_5 else "gemini-1.5-flash"
    )
    log_func("DEBUG", "Gemini", f"Using model: {model_name}")

    gai.configure(api_key=package["apikey"].config.key_gemini())
    model = gai.GenerativeModel(
        "gemini-2.5-flash-preview-04-17",
        system_instruction=prompts_package["template"].GEMINI_TOOL_CALL_INSTRUCTION
        % (original_tools, formatted_tool_names),
        tools=tools,
        tool_config={
            "function_calling_config": {
                "mode": "ANY",
            },
        },
        generation_config=_generation_config,
    )
    response = await model.generate_content_async(
        gemini_messages, safety_settings=_safety_settings
    )
    function_calls = []

    for part in response.candidates[0].content.parts:
        if hasattr(part, "function_call") and part.function_call:
            function_calls.append(part.function_call)

    log_func("DEBUG", "Gemini", f"Function calls: {function_calls}")

    if function_calls:
        return response.candidates[0].content.parts, function_calls

    _assert_safety(response)

    return response.text, None


def _assert_safety(response):
    reason = response.candidates[0].finish_reason
    if reason.value == FinishReason.SAFETY.value:
        reasons = ""
        for safety in response.candidates[0].safety_ratings:
            if safety.blocked:
                reasons += f"{safety.category.name}: {safety.blocked}\n"
        raise Exception(f"Content blocked due to safety concerns:\n{reasons}")


async def chat_gemini_with_tools(
    messages_original,
    tools,
    tool_call_processor,
    system_instruction,
    fallback_1_5=False,
):
    model_response, tool_calls = await chat_gemini_tool_call(
        messages_original, tools, system_instruction, fallback_1_5
    )

    def check_if_skip(tool_calls):
        for tool_call in tool_calls:
            if tool_call.name == "skip_tool_call":
                return True
        return False

    if tool_calls and not check_if_skip(tool_calls):
        tool_result = {
            "response": model_response,
            "result": {},
        }

        for tool_call in tool_calls:
            tool_name = tool_call.name
            tool_params = tool_call.args
            try:
                tool_result["result"][tool_name] = await tool_call_processor(
                    tool_name, tool_params
                )
            except Exception as e:
                log_func("ERROR", "Gemini", f"Error calling tool {tool_name}: {e}")
                tool_result["result"][tool_name] = f"Failed to call tool: {e}"

        model_response = await chat_gemini(
            messages_original, system_instruction, fallback_1_5, tool_result
        )
    if tool_calls and check_if_skip(tool_calls):
        model_response = await chat_gemini(
            messages_original, system_instruction, fallback_1_5
        )

    return model_response


async def __test__():
    log_func("INFO", "Gemini", "Testing...")
    messages = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I am fine, thank you."},
    ]
    system_instruction = "This is a test."
    response = await chat_gemini(messages, system_instruction)
    log_func("INFO", "Gemini", "Response: ", response)
