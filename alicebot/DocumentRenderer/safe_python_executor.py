import os
import sys
import io
import base64
import time
import multiprocessing
import tempfile
import traceback
from multiprocessing import Process, Queue, get_context
import RestrictedPython
from RestrictedPython import compile_restricted
import matplotlib

matplotlib.use('Agg')  # 必须在所有matplotlib导入之前设置
import matplotlib.pyplot as plt
import numpy as np
import math
import random
import datetime as dt
import re

from typing import Callable, Any

log_func: Callable[[Any], None]

# ----------------------
# 跨平台初始化部分
# ----------------------
# 检测操作系统类型
IS_WINDOWS = sys.platform.startswith('win')

# 预加载所有需要的模块
_ = plt.figure()  # 初始化matplotlib后端
plt.close('all')  # 立即关闭初始图形

# ----------------------
# 安全执行环境配置
# ----------------------
SAFE_GLOBALS = {
    '__builtins__': {
        'abs': abs, 'all': all, 'any': any, 'len': len, 'max': max, 'min': min,
        'pow': pow, 'round': round, 'sum': sum, 'range': range, 'enumerate': enumerate,
        'zip': zip, 'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
        'float': float, 'int': int, 'str': str, 'bool': bool,
    },
    '_getattr_': lambda obj, name, default=None: getattr(obj, name, default) if not name.startswith('_') else default,
    '_getiter_': iter,
    '_iter_unpack_sequence_': lambda seq, n: [next(seq) for _ in range(n)],
    'plt': plt,
    'np': np,
    'math': math,
    'random': random,
    'datetime': dt
}


# ----------------------
# 工具函数
# ----------------------
def remove_imports(code: str) -> str:
    """移除所有import语句的正则表达式版本"""
    return re.sub(
        r'^(\s*)(?:from\s+[\w.]+\s+)?import\s+.*?($|\n)',
        '',
        code,
        flags=re.MULTILINE
    )


# ----------------------
# 子进程执行逻辑（跨平台兼容）
# ----------------------
def _run_code_in_process(source_code: str, result_queue: Queue):
    """子进程实际执行函数"""
    temp_file = None
    try:
        # 使用新的独立figure避免线程冲突
        fig = plt.figure()

        # 编译并执行代码
        byte_code = compile_restricted(source_code, '<inline>', 'exec')
        exec(byte_code, SAFE_GLOBALS)

        # 保存到临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        fig.savefig(temp_file.name, format='png', bbox_inches='tight', dpi=100)
        result_queue.put(("success", temp_file.name))

    except Exception as e:
        tb = traceback.format_exc()
        result_queue.put(("error", f"{str(e)}\n{tb}"))
    finally:
        # 确保资源释放
        plt.close(fig if 'fig' in locals() else None)
        plt.close('all')
        if temp_file:
            temp_file.close()


# ----------------------
# 主执行逻辑（跨平台兼容）
# ----------------------
def execute_with_timeout(source_code: str, timeout: int = 8) -> tuple:
    """带超时的安全执行"""
    # 根据平台选择上下文
    ctx = get_context('spawn' if IS_WINDOWS else 'fork')
    result_queue = ctx.Queue()
    process = ctx.Process(target=_run_code_in_process, args=(source_code, result_queue))

    try:
        process.start()
        process.join(timeout)

        if process.is_alive():
            process.terminate()
            process.join()
            return False, "执行超时", None

        if result_queue.empty():
            return False, "无返回结果", None

        status, payload = result_queue.get()
        if status == "success":
            # 读取临时文件内容并立即删除
            with open(payload, "rb") as f:
                img_data = f.read()
            os.unlink(payload)  # 立即删除临时文件
            return True, "执行成功", img_data
        return False, payload, None

    finally:
        # 确保进程终止
        if process.is_alive():
            process.kill()


# ----------------------
# 对外接口
# ----------------------
def safe_exec(code: str, timeout: int = 30) -> tuple:
    """安全执行Matplotlib代码"""
    try:
        # 预处理代码
        code = remove_imports(code)
        code = f"{code}\nplt.close('all')\n"  # 确保关闭所有图形

        # 执行代码
        success, message, img_data = execute_with_timeout(code, timeout)

        if not success:
            return message, False

        return img_data, True

    except Exception as e:
        log_func('ERROR', 'PyExec', f"Error: {str(e)}")
        return f"系统错误: {str(e)}", False
