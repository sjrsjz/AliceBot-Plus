import time
import json
import pathlib
import base64
from typing import Callable, Any

log_func: Callable[[Any], None]
plugin_context: Any

from loader import moduleloader

# Load dependencies
document_renderer_package = moduleloader.ModuleLoader(
    plugin_context.document_renderer_package_path, log_func=log_func
)
typst_render = document_renderer_package.load_module(
    "typst_render", hot_reload=True, log_func=log_func
)

onebot_package = moduleloader.ModuleLoader(
    plugin_context.onebot_package_path, log_func=log_func
)
onebot_package.load_module("api", hot_reload=True, log_func=log_func)

# Data handling
DATA_DIR = pathlib.Path(__file__).parent / "lu_data"
DATA_FILE = DATA_DIR / "data.json"
BACKGROUND_FILE = DATA_DIR / "background.png"

def load_data():
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_background_base64():
    """Load background image bytes"""
    if BACKGROUND_FILE.exists():
        try:
            with open(BACKGROUND_FILE, "rb") as f:
                return f.read()
        except Exception:
            return None
    return None

def get_background_path():
    """Get background image path if exists"""
    if BACKGROUND_FILE.exists():
        return str(BACKGROUND_FILE.absolute()).replace("\\", "/")
    return None

# Lu characters
LU_CHARS = set("撸噜卢芦庐垆泸炉颅鲁卤虏橹路露鹿陆录绿禄碌麓鹭潞璐逯栌胪鸬辘氇舻戮漉簏醁錴鏴騄鵦鵱鸕黸🦌")

class Plugin:
    @staticmethod
    def help():
        return "发送拼音为lu的单个汉字进行🦌管打卡"

    @staticmethod
    def description():
        return "🦌管打卡插件"

    @staticmethod
    def create():
        pass

    @staticmethod
    def destroy():
        pass

    @staticmethod
    def before_reload():
        pass

    @staticmethod
    def after_reload():
        pass

    @staticmethod
    async def on_group_message(ws, message):
        api = onebot_package['api'].OneBotAPI(ws, plugin_context.echo_pool)

        # Check if message is a single "lu" character
        raw_msg = message.get("raw_message", "").strip()
        if len(raw_msg) != 1 or raw_msg not in LU_CHARS:
            return

        user_id = str(message["user_id"])
        group_id = message["group_id"]
        nickname = message.get("sender", {}).get("nickname", f"用户{user_id}")

        data = load_data()
        today = time.strftime("%Y-%m-%d")
        current_month = time.strftime("%Y-%m")

        # Initialize user data if not exists
        if user_id not in data:
            data[user_id] = {
                "count": 0,
                "last_checkin": "",
                "daily": {},  # {date: count}
                "monthly": {}  # {month: count}
            }

        # Migrate old data format
        if "daily" not in data[user_id]:
            data[user_id]["daily"] = {}
        if "monthly" not in data[user_id]:
            data[user_id]["monthly"] = {}

        # Always increment count (allow multiple check-ins per day)
        data[user_id]["count"] += 1
        data[user_id]["last_checkin"] = today

        # Update daily count
        if today not in data[user_id]["daily"]:
            data[user_id]["daily"][today] = 0
        data[user_id]["daily"][today] += 1

        # Update monthly count
        if current_month not in data[user_id]["monthly"]:
            data[user_id]["monthly"][current_month] = 0
        data[user_id]["monthly"][current_month] += 1

        save_data(data)

        # Generate Typst image
        count = data[user_id]["count"]
        daily_count = data[user_id]["daily"].get(today, 0)
        monthly_count = data[user_id]["monthly"].get(current_month, 0)

        # Calculate rankings
        all_users = [(uid, udata["count"]) for uid, udata in data.items()]
        all_users.sort(key=lambda x: x[1], reverse=True)
        user_rank = next((i + 1 for i, (uid, _) in enumerate(all_users) if uid == user_id), 0)
        total_users = len(all_users)

        # Daily rankings
        daily_users = [(uid, udata["daily"].get(today, 0)) for uid, udata in data.items()]
        daily_users = [(uid, cnt) for uid, cnt in daily_users if cnt > 0]
        daily_users.sort(key=lambda x: x[1], reverse=True)
        daily_rank = next((i + 1 for i, (uid, _) in enumerate(daily_users) if uid == user_id), 0)

        # Monthly rankings
        monthly_users = [(uid, udata["monthly"].get(current_month, 0)) for uid, udata in data.items()]
        monthly_users = [(uid, cnt) for uid, cnt in monthly_users if cnt > 0]
        monthly_users.sort(key=lambda x: x[1], reverse=True)
        monthly_rank = next((i + 1 for i, (uid, _) in enumerate(monthly_users) if uid == user_id), 0)

        def escape_string(string: str):
            # 转义
            string = string.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
            return string

        # Load background image
        bg_bytes = load_background_base64()

        # Build typst code following lu.typ template
        typst_code = f"""#set page(width: 720pt, height: 540pt, margin: 0pt)
#set text(font: ("Noto Sans CJK SC", "SimHei", "Microsoft YaHei", "Arial"), lang: "zh")

// Helper functions for CJK number conversion
#let cjk-mapping = (
  "1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
  "6": "六", "7": "七", "8": "八", "9": "九", "0": "〇",
)

#let month-cjk-mapping = (
  "1": "一月", "2": "二月", "3": "三月", "4": "四月", "5": "五月", "6": "六月",
  "7": "七月", "8": "八月", "9": "九月", "10": "十月", "11": "十一月", "12": "十二月",
)

#let day-cjk-mapping = (
  "1": "一日", "2": "二日", "3": "三日", "4": "四日", "5": "五日",
  "6": "六日", "7": "七日", "8": "八日", "9": "九日", "10": "十日",
  "11": "十一日", "12": "十二日", "13": "十三日", "14": "十四日", "15": "十五日",
  "16": "十六日", "17": "十七日", "18": "十八日", "19": "十九日", "20": "二十日",
  "21": "二十一日", "22": "二十二日", "23": "二十三日", "24": "二十四日", "25": "二十五日",
  "26": "二十六日", "27": "二十七日", "28": "二十八日", "29": "二十九日", "30": "三十日",
  "31": "三十一日",
)

#let int-to-cjk = n => {{
  let str-n = str(n)
  let cjk-str = ""
  for ch in str-n {{
    if ch in cjk-mapping {{
      cjk-str = cjk-str + cjk-mapping.at(ch)
    }} else {{
      cjk-str = cjk-str + ch
    }}
  }}
  cjk-str
}}

// Background gradient
#place(
  center + horizon,
  rect(
    width: 720pt,
    height: 540pt,
    fill: gradient.linear(
      rgb("#ff5001"),
      rgb("#ffff01"),
      rgb("#ffff01"),
      rgb("#ff5001"),
      angle: 180deg,
    ),
  ),
)

// Left decorative lines
#place(center + horizon, dx: -270pt, rect(width: 5pt, height: 540pt, fill: rgb("#ff8001d0")))
#place(center + horizon, dx: -260pt, rect(width: 5pt, height: 540pt, fill: rgb("#ff8001d0")))
#place(center + horizon, dx: -245pt, rect(width: 7.5pt, height: 540pt, fill: rgb("#ff8001d0")))

// Right decorative lines
#place(center + horizon, dx: 270pt, rect(width: 5pt, height: 540pt, fill: rgb("#ff8001d0")))
#place(center + horizon, dx: 260pt, rect(width: 5pt, height: 540pt, fill: rgb("#ff8001d0")))
#place(center + horizon, dx: 245pt, rect(width: 7.5pt, height: 540pt, fill: rgb("#ff8001d0")))

#align(center + horizon)[
  // Title
  #text("奖", size: 60pt, weight: "bold", fill: rgb("#ffffff00"), stroke: 3.5pt + rgb("#e1681d"))
  #h(100pt)
  #text("🦌", size: 60pt, weight: "bold", fill: rgb("#ff5001"))
  #h(100pt)
  #text("状", size: 60pt, weight: "bold", fill: rgb("#ffffff00"), stroke: 3.5pt + rgb("#e1681d"))

  #place(dx: 100pt, dy: 10pt, text(size: 20pt, [恭喜 #"{nickname}" 同学累计已撸：]))

  #v(60pt)

  // Main count
  #text(size: 44pt, weight: "black", fill: gradient.linear(rgb("#DC143C"), rgb("#8B0000"), angle: 180deg), stroke: 1.5pt + rgb("#DAA520"))[
    第 {count} 管
  ]

  // Statistics grid
  #grid(
    columns: (3fr, 1fr, 3fr),
    column-gutter: 0pt,
    row-gutter: 12pt,

    // Today's stats
    box(radius: 10pt, inset: 12pt, width: 100%)[
      #align(center)[
        #text(size: 12pt, fill: rgb("#8B0000"), weight: "bold")[今日打卡]

        #text(size: 22pt, weight: "black", fill: rgb("#FF8C00"))[{daily_count} 次]
        
        #text(size: 10pt, fill: rgb("#DC143C"), weight: "bold")[排名 {daily_rank}]
      ]
    ],

    // Overall ranking
    box(radius: 12pt, inset: (x: 15pt, y: 8pt))[
      #text(size: 13pt, fill: rgb("#8B0000"), weight: "bold")[总排名]

      #text(size: 18pt, weight: "black", fill: rgb("#DC143C"))[{user_rank} / {total_users}]
    ],

    // Monthly stats
    box(radius: 10pt, inset: 12pt, width: 100%)[
      #align(center)[
        #text(size: 12pt, fill: rgb("#8B0000"), weight: "bold")[本月打卡]
        
        #text(size: 22pt, weight: "black", fill: rgb("#FF8C00"))[{monthly_count} 次]
        
        #text(size: 10pt, fill: rgb("#DC143C"), weight: "bold")[排名 {monthly_rank}]
      ]
    ],
  )
"""

        # Add background image if exists
        if bg_bytes:
            bytes_array = ", ".join(str(b) for b in bg_bytes)
            typst_code += f"""
  #place(center, image.decode(bytes(({bytes_array})), format: "png", width: 720pt), dy: -25pt)
"""

        # Add date
        import datetime
        now = datetime.datetime.now()
        month_str = str(now.month)
        day_str = str(now.day)

        typst_code += f"""
  #h(300pt)
  #text(size: 20pt, fill: gradient.linear(rgb("#8B4513"), rgb("#ffff01"), angle: 180deg), style: "italic", weight: "medium")[
    #int-to-cjk({now.year})年#month-cjk-mapping.at("{month_str}")#day-cjk-mapping.at("{day_str}") 颁
  ]
]
"""
        try:
            img_bytes = typst_render.render(typst_code)
            img_base64 = base64.b64encode(img_bytes).decode()
            cq_code = f"[CQ:image,file=base64://{img_base64}]"
            await api.send_group_message(group_id, message=cq_code)
        except Exception as e:
            log_func("ERROR", "LuPlugin", f"Render failed: {e}")
            # Fallback to text
            await api.send_group_message(
                group_id, 
                message=f"打卡成功！\n今日: {daily_count}次 (#{daily_rank})\n本月: {monthly_count}次 (#{monthly_rank})\n总计: {count}次 (#{user_rank}/{total_users})"
            )
        raise plugin_context.SkipFollow()
