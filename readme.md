<div align="center">
  <h1><img src="image/readme/1740150452111.jpg" width="28px" height="auto" alt="AliceBot Logo" style="vertical-align: middle;"> AliceBot+</h1>
  <p>
    <strong>QQ bot powered by AI</strong>
  </p>
</div>

---

#### **AliceBot+** 是一个基于 OneBot v11 标准的 QQ 机器人，基于非开源的原始版本重构而来，目的是为了提供更清晰的代码结构和更好的可维护性。同时提供插件系统，方便用户自定义功能。

## 🔧 功能
- [x] 🤖 通过 **OneBot v11** 标准接收和发送消息
- [x] 🔌 NapCatQQ/Lagrange.OneBot Websocket API支持
- [x] 📝 编解码 CQ 码
- [x] 👥 群聊消息处理
- [x] 🔄 自身局部代码热重载
- [x] 🖥️ 基于 Rich 库的可交互 TUI
- [x] 🧠 高度可扩展定制化AI提示词模板
- [x] 🎨 AI 格式化富文本输出，CoT 推理，基于 Flux.1 的绘图
- [x] 📊 文档渲染器 (支持 Markdown/HTML/LaTeX/Typst，基于无头浏览器和 Matplotlib)
- [x] 🔍 网页搜索、读取解析
- [x] 🧩 插件系统
- [x] 💾 上下文管理器，自动缓存上下文
- [x] ⏱️ 限速器 (针对 AI 模型，自动根据历史调用频次计算 CD)
- [x] 🤖 AI 模型支持，支持自动搜索网页和语音生成等，默认提示词模板支持自动建立用户档案
- [x] 🔧 复杂指令解析 (基于 [fJson](https://github.com/sjrsjz/fJson))
- [x] 🌐 简易 WebUI
- [ ] 💬 私聊消息处理 (它真的会被支持吗？)

## 🚀快速开始
### 🏃‍♂️ 运行
由于项目采用 Python 包的方式进行源代码组织，因此建议使用以下方式进行运行：

```bash
# 克隆项目
git clone https://github.com/sjrsjz/AliceBot-Plus
# 进入项目目录
cd AliceBot-Plus

# 创建虚拟环境
python -m venv python_env
# 激活虚拟环境（Linux/macOS）
source python_env/bin/activate
# 激活虚拟环境（Windows）
# python_env\Scripts\activate

# 安装依赖
pip install -r requirements.txt
# 运行
python -m alicebot
```

### ⚙️ 配置文件
`plugins/meta.json` 是插件的元数据文件，用于描述插件的基本状态和信息。在插件加载时，会读取该文件进行插件权限和启用状态的判断。

```json
{
    "meta": {
        "test": { // 插件名（文件名）
            "active": 1, // 是否启用
            "permission": 0, // 权限等级, 0 为所有人可用, 1 为Bot管理员可用
            "priority": 0 // 插件优先级, 越高越先执行，默认为 0
        },
        "help": {
            "active": 1,
            "permission": 0,
            "priority": 0
        }
    }
}
```
`config/bot_config.json` 是配置文件，用于配置机器人的基本信息。

```json
{
    "admins": [], // 管理员QQ号
    "browser_path": "/usr/bin/chromium" // 无头浏览器路径
}
```

`config/protocol.json` 是协议/网络配置文件，用于配置机器人的协议信息。

```json
{
    "ws_url": "ws://127.0.0.1:8080", // OneBotAPI地址
    "webui_port": 8081 // WebUI端口，监听 0.0.0.0
}

`interface/webui-config/users.json` 是WebUI的用户配置文件，用于配置WebUI的用户信息。

```json
{
    "SHA256 hashed username": "SHA256 hashed password",
}
```

`aibackend/keys/apikey.json` 是AI后端的API Key配置文件，用于配置AI后端的API Key信息。

```json
{
    "gemini": [], // Gemini API Key，从谷歌AI平台获取
    "gemini_index": 0,
    "siliconflow": [], // SiliconFlow API Key，从硅基流动平台获取
    "siliconflow_index": 0
}
```

## 📦插件
插件是 AliceBot+ 的核心功能，通过插件可以实现机器人的各种功能。插件的基本结构如下：

```python
from typing import Callable, Any
log_func: Callable[[Any], None] # 日志记录函数
plugin_context: Any # 插件上下文，由插件管理器传入

'''
# 插件上下文定义
class PluginContext:
    def __init__(
        self,
        bot_entity,
        plugin_meta,
        Skip,
        SkipFollow,
        timeout,
        ratelimit,
        async_ratelimit,
        RateLimitedError,
        RateLimiter,
        echo_pool,
        onebot_package_path=onebot_package_path,
        message_codec_package_path=message_codec_package_path,
        aibackend_package_path=aibackend_package_path,
        prompt_package_path=prompt_package_path,
        document_renderer_package_path=document_renderer_package_path,
    ):
        self.bot_entity = bot_entity # 机器人实体
        self.plugin_meta = plugin_meta # 插件元数据
        self.Skip = Skip # 跳过本插件，通过 raise Skip() 调用
        self.SkipFollow = SkipFollow # 跳过后续插件，通过 raise SkipFollow() 调用
        self.timeout = timeout # 超时装饰器
        self.ratelimit = ratelimit # 限速装饰器
        self.async_ratelimit = async_ratelimit # 异步限速装饰器
        self.RateLimitedError = RateLimitedError # 限速错误
        self.RateLimiter = RateLimiter # 限速器
        self.echo_pool = echo_pool # 回显池
        self.onebot_package_path = onebot_package_path # OneBotAPI包路径
        self.message_codec_package_path = message_codec_package_path # 消息编解码包路径
        self.aibackend_package_path = aibackend_package_path # AI后端包路径
        self.prompt_package_path = prompt_package_path # 提示词包路径
        self.document_renderer_package_path = document_renderer_package_path # 文档渲染器包路径

'''


from loader import moduleloader # 热重载器，用于加载模块


onebot_package = moduleloader.ModuleLoader(plugin_context.onebot_package_path, log_func=log_func) # 加载OneBotAPI包
onebot_package.load_module("api", hot_reload=True, log_func=log_func) # 加载OneBot API模块

message_codec_package = moduleloader.ModuleLoader(plugin_context.message_codec_package_path, log_func=log_func) # 加载消息编解码包
message_codec_package.load_module("codec", hot_reload=True, log_func=log_func) # 加载消息编解码模块


log_func('INFO', 'TEST', r'''
This is a test plugin for AliceBot+.
''') # 记录日志

class Plugin: # 插件类（必须）
    @staticmethod
    def help(): # 帮助信息
        return 'Help message.'

    @staticmethod
    def description(): # 插件描述
        return 'Test plugin.'

    @staticmethod
    def create(): # 插件创建时调用
        log_func('INFO', 'TEST', "Plugin created.")

    @staticmethod
    def destroy(): # 插件销毁时调用
        log_func('INFO', 'TEST', "Plugin destroyed.")

    @staticmethod
    def before_reload(): # 插件热重载前调用
        log_func('INFO', 'TEST', "Plugin before reload.")

    @staticmethod
    def after_reload(): # 插件热重载后调用
        log_func('INFO', 'TEST', "Plugin after reload.")

    @staticmethod
    async def on_group_message(ws, message): # 群聊消息处理
        api = onebot_package['api'].OneBotAPI(ws, plugin_context.echo_pool) # 获取OneBot API实例
        async def timeout_callback(): # 超时回调
            pass

        @plugin_context.timeout(5, timeout_callback=timeout_callback) # 设置超时时间（秒）和超时回调
        async def handler(): # 消息处理
            encoded_message = await message_codec_package['codec'].encode_message_to_CQ(message["message"]) # 编码消息到CQ码
            if "test" in encoded_message:
                await api.send_group_message(message["group_id"], message=encoded_message) # 发送群消息
            
        await handler() # 调用消息处理

```

## 📜 开源许可
本项目采用 [MIT](LICENSE) 开源许可证。 🎉