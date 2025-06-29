import asyncio
import aiohttp
import aiohttp.web
import websockets
import threading
import json
import websockets.client
import os
import urllib.parse
import random
import traceback
import base64
import pathlib

clients = set()


class WebUI:
    def __init__(self, port, log_provider, log_func):
        self.port = port
        self.app = None
        self.runner = None
        self.site_ipv4 = None
        self.shutdown_event = asyncio.Event()
        self.log_provider = log_provider
        self.webui_thread = None
        self.log_func = log_func
        self.webui_close_signal = threading.Event()
        self.webui_close_signal.clear()

    async def serve(self):
        self.app = aiohttp.web.Application()
        self.app.add_routes([aiohttp.web.get('/logs', self.get_html)])
        self.app.add_routes([aiohttp.web.get('/', self.redirect)])
        self.app.add_routes([aiohttp.web.get('/ws', self.ws_handler)])
        self.app.add_routes([aiohttp.web.get('/login', self.get_login)])
        self.app.add_routes([aiohttp.web.get('/ws/ws-warpper', self.ws_warpper)])

        self.runner = aiohttp.web.AppRunner(self.app)

        await self.runner.setup()
        self.site_ipv4 = aiohttp.web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site_ipv4.start()
        self.log_func("INFO", "WebUI", f"WebUI started at https://0.0.0.0:{self.port}")
        await self.shutdown_event.wait()

    async def ws_warpper(self, request):
        websocket = aiohttp.web.WebSocketResponse()
        await websocket.prepare(request)
        async for message in websocket:
            try:
                data = json.loads(message.data)
                if data["type"] == "POST":
                    response = await self.ws_post_warpper(data)
                    await websocket.send_str(response.text)
                elif data["type"] == "GET":
                    response = await self.ws_get_warpper(data)
                    await websocket.send_str(response.text)
            except Exception as e:
                await websocket.send_str(str(e))
        return websocket

    async def ws_post_warpper(self, data):
        self.log_func("INFO", "WebUI", "POST request received:", data)
        try:
            headers = data["headers"]
        except:
            headers = {}
        url = data["url"]
        post_data = data["post_data"]
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=post_data) as response:
                self.log_func(
                    "INFO", "WebUI", "Response:", await response.text()
                )
                return aiohttp.web.Response(text=await response.text())

    async def ws_get_warpper(self, data):
        self.log_func("INFO", "WebUI", "GET request received:", data)
        try:
            try:
                headers = data["headers"]
            except:
                headers = {}
            url = data["url"]
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    self.log_func("INFO", "WebUI", "Response:", await response.text())
                    return aiohttp.web.Response(text=await response.text())
        except:
            self.log_func("ERROR", "WebUI", traceback.format_exc()) 
            return aiohttp.web.Response(text="Error")

    async def get_forbidden_html(self):
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Forbidden</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #f8d7da;
            color: #721c24;
        }
        h1 {
            font-size: 3rem;
            margin: 0;
            padding: 20px;
            border: 2px solid #f5c6cb;
            border-radius: 10px;
            background-color: #f5c6cb;
        }
    </style>
</head>
<body>
    <h1>403 Forbidden</h1>
</body>
</html>
"""

    async def redirect(self, request):
        return aiohttp.web.HTTPFound('/login')

    def run_http_server(self):
        asyncio.run(self.serve())

    async def get_login(self, request):

        username = request.query.get('username')
        password = request.query.get('password')
        if username or password:
            try:
                await self.check_login(username, password)
            except Exception as e:
                self.log_func("WARN", "WebUI", f"Login failed: {e}")
                return aiohttp.web.HTTPFound('/login?error='+urllib.parse.quote(str(e)))

        login_page = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Login Page</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #f4f4f4;
        }
        form {
            width: 300px;
            padding: 20px;
            background-color: white;
            border: 1px solid #ccc;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ccc;
            border-radius: 3px;
            box-sizing: border-box;
        }
        button {
            width: 100%;
            padding: 10px;
            background-color: #007BFF;
            color: white;
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }
        button:hover {
            background-color: #0056b3;
        }
        .error {
            color: red;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <form id="login-form">
        <h2>Login</h2>
        <div id="error-message" class="error"></div>
        <input type="text" id="username" placeholder="Username" required>
        <input type="password" id="password" placeholder="Password" required>
        <button type="submit">Login</button>
    </form>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.0.0/crypto-js.min.js"></script>
    <script>
        document.getElementById('login-form').addEventListener('submit', async function(event) {
            event.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            // Simple encryption function (for demonstration purposes only)
            const encryptedUsername = CryptoJS.SHA256(username).toString();
            const encryptedPassword = CryptoJS.SHA256(password).toString();

            const response = await fetch('/login', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                },
                params: JSON.stringify({ username: encryptedUsername, password: encryptedPassword })
            });

            if (response.ok) {
                window.location.href = `/logs?username=${encryptedUsername}&password=${encryptedPassword}`;
            } else {
                alert('Login failed.', response.statusText);
            }
        });

        // Function to get URL parameters
        function getUrlParameter(name) {
            name = name.replace(/[\\[]/, '\\[').replace(/[\\]]/, '\\]');
            const regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
            const results = regex.exec(location.search);
            return results === null ? '' : decodeURIComponent(results[1].replace(/\\+/g, ' '));
        }

        // Display error message if present in URL parameters
        const errorMessage = getUrlParameter('error');
        if (errorMessage) {
            document.getElementById('error-message').textContent = errorMessage;
        }
    </script>
</body>
</html>
"""
        return aiohttp.web.Response(text=login_page, content_type='text/html')

    async def check_login(self, username, password):
        # Check the login credentials.
        # 检查登录凭证
        self.log_func("INFO", "WebUI", "Checking login credentials...")
        self.log_func("INFO", "WebUI", "username:", username)
        user_json = {}
        users_file = pathlib.Path(os.path.dirname(__file__) + "/webui-config/users.json")
        if not users_file.exists():
            users_file.parent.mkdir(parents=True, exist_ok=True)
            with open(users_file, "w", encoding="utf-8") as f:
                f.write("{}")
        with open(users_file , "r", encoding="utf-8") as f:
            user_json = json.load(f)
        if username in user_json:
            if user_json[username] == password:
                self.log_func("INFO", "WebUI", "Login successful")
                return True
            else:
                self.log_func("WARN", "WebUI", "Password incorrect")
                self.log_func("WARN", "WebUI", "Password:", password)
                raise Exception("Password incorrect")
        else:
            self.log_func("WARN", "WebUI", "User not found")
            raise Exception("User not found")
    async def get_html(self, request):
        self.log_func("INFO", "WebUI", "New client connected:", request.remote)
        # 获取登录参数
        username = request.query.get('username')
        password = request.query.get('password')

        try:
            await self.check_login(username, password)
        except Exception as e:
            self.log_func("WARN", "WebUI", f"Login failed: {e}")

            return aiohttp.web.HTTPFound('/login?error='+urllib.parse.quote(str(e)))
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Bot WebUI</title>
            <style>
                :root {{
                    --bg-color: #f8f9fa;
                    --container-bg: #ffffff;
                    --text-color: #333333;
                    --border-color: #dee2e6;
                    --header-color: #495057;
                    --accent-color: #007bff;
                    --table-header-bg: #e9ecef;
                    --warning-color: #ffc107;
                    --danger-color: #dc3545;
                    --success-color: #28a745;
                    --shadow-color: rgba(0, 0, 0, 0.1);
                    --error-color: #dc3545;
                }}

                [data-theme="dark"] {{
                    --bg-color: #212529;
                    --container-bg: #343a40;
                    --text-color: #f8f9fa;
                    --border-color: #495057;
                    --header-color: #e9ecef;
                    --accent-color: #0d6efd;
                    --table-header-bg: #495057;
                    --shadow-color: rgba(255, 255, 255, 0.05);
                }}

                * {{
                    box-sizing: border-box;
                    transition: background-color 0.3s, color 0.3s;
                }}

                body {{
                    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    min-height: 100vh;
                    font-size: 1rem;
                    background-color: var(--bg-color);
                    color: var(--text-color);
                    line-height: 1.5;
                }}

                h1 {{
                    margin: 20px 0;
                    color: var(--header-color);
                    font-weight: 600;
                }}

                #top-bar {{
                    width: 90%;
                    max-width: 1200px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }}

                #theme-toggle {{
                    background: none;
                    border: 1px solid var(--border-color);
                    border-radius: 20px;
                    padding: 5px 15px;
                    cursor: pointer;
                    color: var(--text-color);
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}

                #container {{
                    width: 90%;
                    max-width: 1200px;
                    display: flex;
                    flex-direction: column;
                    align-items: stretch;
                    height: calc(80vh);
                    box-sizing: border-box;
                    border: 1px solid var(--border-color);
                    border-radius: 12px;
                    background-color: var(--container-bg);
                    box-shadow: 0 4px 12px var(--shadow-color);
                    margin: 0 auto 20px auto;
                    padding: 20px;
                }}

                #info {{
                    display: flex;
                    flex-wrap: wrap;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    gap: 10px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid var(--border-color);
                }}

                .info-item {{
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}

                .info-label {{
                    font-weight: 500;
                }}

                #tasks-container {{
                    flex: 0 0 40%;
                    overflow-y: auto;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    padding: 15px;
                    background-color: var(--container-bg);
                    margin-bottom: 15px;
                    height: 40%;
                }}

                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 0.9rem;
                }}

                th, td {{
                    border: 1px solid var(--border-color);
                    padding: 10px;
                    text-align: left;
                }}

                th {{
                    background-color: var(--table-header-bg);
                    font-weight: 600;
                    position: sticky;
                    top: 0;
                }}
                
                td {{
                    vertical-align: top;
                }}

                .message-cell {{
                    max-width: 400px;
                    white-space: normal;
                    word-break: break-word;
                }}

                .message-json {{
                    background-color: var(--bg-color);
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid var(--border-color);
                    overflow: auto;
                    max-height: 200px;
                }}

                .message-property {{
                    font-weight: 500;
                    color: var(--accent-color);
                }}

                .message-value {{
                    color: var(--success-color);
                }}

                .json-string {{
                    color: var(--success-color);
                }}

                .json-number {{
                    color: var(--warning-color);
                }}

                .json-boolean {{
                    color: var(--accent-color);
                }}

                .json-null {{
                    color: var(--danger-color);
                }}

                .error {{
                    color: var(--error-color);
                    margin-top: 10px;
                    font-weight: 500;
                    text-align: center;
                }}

                .btn {{
                    padding: 8px 16px;
                    border-radius: 4px;
                    border: none;
                    cursor: pointer;
                    font-weight: 500;
                    transition: background-color 0.2s, transform 0.1s;
                }}

                .btn:hover {{
                    transform: translateY(-1px);
                }}

                .btn:active {{
                    transform: translateY(1px);
                }}

                .btn-danger {{
                    background-color: var(--danger-color);
                    color: white;
                }}

                .btn-danger:hover {{
                    background-color: #c82333;
                }}

                /* Media queries for responsive design */
                @media (max-width: 768px) {{
                    #container {{
                        width: 95%;
                    }}
                    
                    #info {{
                        flex-direction: column;
                        align-items: flex-start;
                    }}
                    
                    table {{
                        font-size: 0.8rem;
                    }}
                    
                    th, td {{
                        padding: 8px 4px;
                    }}
                }}
                #log {{
                    flex: 1;
                    overflow-y: auto;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    padding: 10px;
                    background-color: var(--container-bg);
                    margin-bottom: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 0.9rem;
                    line-height: 1.4;
                }}

                .log-line {{
                    transition: background-color 0.2s;
                }}

                .log-line:hover {{
                    background-color: rgba(0, 0, 0, 0.05);
                }}

                [data-theme="dark"] .log-line:hover {{
                    background-color: rgba(255, 255, 255, 0.05);
                }}

                .log-info {{
                    border-left-color: var(--accent-color);
                }}

                .log-warn {{
                    border-left-color: var(--warning-color);
                }}

                .log-debug {{
                    border-left-color: var(--success-color);
                }}

                .log-error{{
                    border-left-color: var(--danger-color);
                    background-color: rgba(220, 53, 69, 0.05);
                }}

                [data-theme="dark"] .log-error {{
                    background-color: rgba(220, 53, 69, 0.1);
                }}
                
            </style>
        </head>
        <body>
            <div id="top-bar">
                <h1>Bot WebUI</h1>
                <button id="theme-toggle" class="btn">
                    <span id="theme-icon">🌙</span>
                    <span id="theme-text">暗黑模式</span>
                </button>
            </div>

            <div id="container">
                <div id="info">
                    <div class="info-item">
                        <span class="info-label">CPU使用率:</span>
                        <span id="cpu_percent" class="info-value">0%</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">内存使用率:</span>
                        <span id="memory_percent" class="info-value">0%</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">运行中任务:</span>
                        <span id="running_tasks" class="info-value">0</span>
                    </div>
                    <button id="restart-button" class="btn btn-danger">重启系统</button>
                </div>

                <div id="tasks-container">
                    <table id="tasks">
                        <thead>
                            <tr>
                                <th>任务名称</th>
                                <th>持续时间(秒)</th>
                                <th>开始时间</th>
                                <th>消息内容</th>
                            </tr>
                        </thead>
                        <tbody>
                        </tbody>
                    </table>
                </div>
                <pre id="log"></pre>
                <div id="error-message" class="error"></div>
            </div>

            <script>
                let socket;
                let darkMode = localStorage.getItem('darkMode') === 'true';
                
                // 初始化主题设置
                if (darkMode) {{
                    document.body.setAttribute('data-theme', 'dark');
                    document.getElementById('theme-icon').textContent = '☀️';
                    document.getElementById('theme-text').textContent = '亮色模式';
                }}
                
                // 切换主题
                document.getElementById('theme-toggle').addEventListener('click', function() {{
                    darkMode = !darkMode;
                    if (darkMode) {{
                        document.body.setAttribute('data-theme', 'dark');
                        document.getElementById('theme-icon').textContent = '☀️';
                        document.getElementById('theme-text').textContent = '亮色模式';
                    }} else {{
                        document.body.removeAttribute('data-theme');
                        document.getElementById('theme-icon').textContent = '🌙';
                        document.getElementById('theme-text').textContent = '暗黑模式';
                    }}
                    localStorage.setItem('darkMode', darkMode);
                }});

                // 格式化JSON显示
                function formatJSON(json) {{
                    if (typeof json !== 'object' || json === null) {{
                        try {{
                            json = JSON.parse(json);
                        }} catch (e) {{
                            return String(json);
                        }}
                    }}
                    
                    let html = '<div class="message-json">';
                    
                    for (const key in json) {{
                        if (json.hasOwnProperty(key)) {{
                            html += '<div>';
                            html += `<span class="message-property">${{key}}:</span> `;
                            
                            if (typeof json[key] === 'object' && json[key] !== null) {{
                                html += formatJSON(json[key]);
                            }} else {{
                                html += formatValue(json[key]);
                            }}
                            
                            html += '</div>';
                        }}
                    }}
                    
                    html += '</div>';
                    return html;
                }}
                
                function formatValue(value) {{
                    if (typeof value === 'string') {{
                        return `<span class="json-string">"${{value}}"</span>`;
                    }} else if (typeof value === 'number') {{
                        return `<span class="json-number">${{value}}</span>`;
                    }} else if (typeof value === 'boolean') {{
                        return `<span class="json-boolean">${{value}}</span>`;
                    }} else if (value === null) {{
                        return `<span class="json-null">null</span>`;
                    }} else {{
                        return String(value);
                    }}
                }}

                function connect() {{
                    const username = getUrlParameter('username');
                    const password = getUrlParameter('password');
                    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
                    
                    socket = new WebSocket(`${{protocol}}://${{window.location.host}}/ws?username=${{username}}&password=${{password}}`);
                    
                    socket.addEventListener('open', function(event) {{
                        console.log('WebSocket连接已建立');
                        document.getElementById('error-message').textContent = '';
                    }});

                    socket.addEventListener('message', function(event) {{
                        const data = JSON.parse(event.data);
                        const log = document.getElementById('log');
                        const tasksTableBody = document.getElementById('tasks').getElementsByTagName('tbody')[0];
                        const cpuPercent = document.getElementById('cpu_percent');
                        const memoryPercent = document.getElementById('memory_percent');
                        const runningTasks = document.getElementById('running_tasks');

                        // 更新任务表格
                        tasksTableBody.innerHTML = '';
                        data.tasks_info.running_tasks.forEach(task => {{
                            const row = tasksTableBody.insertRow();
                            const cell1 = row.insertCell(0);
                            const cell2 = row.insertCell(1);
                            const cell3 = row.insertCell(2);
                            const cell4 = row.insertCell(3);
                            
                            cell1.textContent = task.task_name;
                            cell2.textContent = Math.floor(task.task_duration * 1000) / 1000;
                            
                            const startTime = new Date(task.task_start_time * 1000);
                            const formattedStartTime = startTime.toLocaleString();
                            cell3.textContent = formattedStartTime;
                            
                            cell4.className = 'message-cell';
                            try {{
                                cell4.innerHTML = formatJSON(task.message);
                            }} catch (e) {{
                                cell4.textContent = JSON.stringify(task.message);
                            }}
                        }});

                        // 更新日志
                        if ('log_text' in data) {{
                            const tolerance = 5;
                            const isAtBottom = log.scrollHeight - log.scrollTop <= log.clientHeight + tolerance;
                            
                            // 处理日志文本，添加颜色高亮
                            const logText = data.log_text;
                            const colorizedLog = colorizeLogText(logText);
                            log.innerHTML = colorizedLog;
                            
                            if (isAtBottom) {{
                                log.scrollTop = log.scrollHeight;
                            }}
                        }}
                        
                        // 更新系统信息
                        cpuPercent.textContent = data.tasks_info.cpu_percent + '%';
                        memoryPercent.textContent = data.tasks_info.memory_percent + '%';
                        runningTasks.textContent = data.tasks_info.running_tasks.length;

                        // 根据使用率更新颜色
                        updateUsageColor(cpuPercent, data.tasks_info.cpu_percent);
                        updateUsageColor(memoryPercent, data.tasks_info.memory_percent);
                    }});

                    socket.addEventListener('close', function(event) {{
                        console.log('WebSocket连接已关闭，尝试重新连接...');
                        document.getElementById('error-message').textContent = '连接失败，服务器是否已关闭？';
                        setTimeout(connect, 1000);
                    }});

                    socket.addEventListener('error', function(event) {{
                        console.error('WebSocket错误:', event);
                        socket.close();
                    }});
                }}

                function updateUsageColor(element, percent) {{
                    if (percent < 50) {{
                        element.style.color = 'var(--success-color)';
                    }} else if (percent < 75) {{
                        element.style.color = 'var(--warning-color)';
                    }} else {{
                        element.style.color = 'var(--danger-color)';
                    }}
                }}

                function sendRestartCommand() {{
                    if(confirm('确定要重启系统吗？')) {{
                        if (socket && socket.readyState === WebSocket.OPEN) {{
                            socket.send(JSON.stringify({{ command: 'restart' }}));
                        }} else {{
                            console.error('WebSocket未连接。无法发送重启命令。');
                        }}
                    }}
                }}

                function getUrlParameter(name) {{
                    name = name.replace(/[\\[]/, '\\\\[').replace(/[\\]]/, '\\\\]');
                    const regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
                    const results = regex.exec(location.search);
                    return results === null ? '' : decodeURIComponent(results[1].replace(/\\+/g, ' '));
                }}

                function escapeHtml(unsafe) {{
                    return unsafe
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/\"/g, "&quot;")
                        .replace(/'/g, "&#039;");
                }}
                function colorizeLogText(text) {{
                    if (!text) return '';
                    // 将日志文本按行分割
                    const lines = text.split('\n').filter(line => line.trim() !== '');
                    // 为每行创建独立的样式区块
                    return lines.map(line => {{
                        let logClass = 'log-normal';
                        let logColor = 'var(--text-color)';
                        // 根据日志级别应用不同的样式
                        if (line.includes('[INFO]')) {{
                            logClass = 'log-info';
                            logColor = 'var(--accent-color)';
                        }} else if (line.includes('[WARN]')) {{
                            logClass = 'log-warn';
                            logColor = 'var(--warning-color)';
                        }} else if (line.includes('[DEBUG]')) {{
                            logClass = 'log-debug';
                            logColor = 'var(--success-color)';
                        }} else if (line.includes('[ERROR]')) {{
                            logClass = 'log-error';
                            logColor = 'var(--danger-color)';
                        }}
                        // 先对整行做HTML转义
                        let safeLine = escapeHtml(line);
                        // 提取日志级别标签进行高亮处理
                        const formattedLine = safeLine.replace(/\[(INFO|WARN|DEBUG|ERROR)\]/g, 
                            (match, level) => `<span style="color: ${{logColor}}; font-weight: 600;">[${{level}}]</span>`);
                        // 返回带样式的日志行
                        return `<div class="log-line ${{logClass}}" style="padding: 4px 8px; margin: 2px 0; border-radius: 4px; border-left: 3px solid ${{logColor}}; background-color: var(--bg-color);">${{formattedLine}}</div>`;
                    }}).join('');
                }}
                document.getElementById('restart-button').addEventListener('click', sendRestartCommand);
                connect();
            </script>
        </body>
        </html>
        """
        return aiohttp.web.Response(text=html_content, content_type='text/html')
    def run_ws_server(self):
        asyncio.run(self.serve())

    async def ws_handler(self, request):
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)
        x_forwarded_for = request.headers.get('X-Forwarded-For')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.headers.get('X-Real-IP', request.remote)

        username = request.query.get('username')
        password = request.query.get('password')
        self.log_func("INFO", "WebUI", "Trying to login with username:", username)
        try:
            await self.check_login(username, password)
        except Exception as e:
            self.log_func("WARN", "WebUI", f"Login failed: {e}")
            await ws.close()
            return ws
        self.log_func("INFO", "WebUI", "Login successful")
        clients.add(ws)
        self.log_func("INFO", "WebUI", "New websocket connected:", ip)
        try:
            last_log_text = ""
            async def handle_message(msg):
                data = json.loads(msg.data)
                if data.get("command") == "restart":
                    self.log_func("WARN", "WebUI", "Received restart command")
                    os.system("sudo reboot")
                    # 在这里添加重启逻辑
            async def ws_listener():
                self.log_func("INFO", "WebUI", "Creating new websocket listener...")
                while not self.webui_close_signal.is_set():

                    try:
                        async for msg in ws:
                            await handle_message(msg)
                    except Exception as e:
                        self.log_func("ERROR", "WebUI", "WebSocket error: ", e)
                        break
            asyncio.get_event_loop().create_task(ws_listener())
            while not self.webui_close_signal.is_set():

                log = await self.log_provider()

                log_text = log["log_text"]()
                task_info = await log["tasks_info"]()
                log = {
                    "tasks_info": task_info
                }
                if log_text != last_log_text:
                    log["log_text"] = log_text
                last_log_text = log_text
                log = json.dumps(log)
                await ws.send_str(log)
                await asyncio.sleep(1)  # Sleep for a short interval to avoid flooding the connection.

        except Exception as e:
            self.log_func("ERROR", "WebUI", f"WebSocket error: {e}")
        finally:
            clients.remove(ws)
            await ws.close()
            self.log_func("WARN", "WebUI", "Websocket disconnected:", request.remote)
        return ws

    async def run(self):
        self.log_func(
            "WARN",
            "WebUI",
            "WebUI will expose your bot to the internet, please make sure you have configured the firewall and the SSL certificate properly.",
        )
        self.web_ui_thread = threading.Thread(target=self.run_http_server)
        self.web_ui_thread.start()
        self.log_func("INFO", "WebUI", "WebUI server started")

    async def exit(self):
        # 关闭WebUI
        self.webui_close_signal.set()
        self.shutdown_event.set()

        if self.site_ipv4 and self.site_ipv4._runner:
            await self.site_ipv4.stop()

        await self.runner.cleanup()
        await self.app.shutdown()
        await self.app.cleanup()

        self.web_ui_thread.join()

        self.log_func("INFO", "WebUI", "WebUI closed")
