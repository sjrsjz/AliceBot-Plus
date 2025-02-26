from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich import box
import threading
import time
import wcwidth as wcw
import readchar


class RichTUI:

    def __init__(self, status_bar_setter, server_close_event = None, log_file = None):
        self.console = Console()
        self.log_buffer = []
        self.log_index = 0
        self.log_area = Panel(Text(), title="Log", box=box.SIMPLE)
        self.status_bar = Text()
        self.layout = Layout()
        self.layout.split(
            Layout(name="log_area"),
            Layout(name="status_bar", size=1)
        )
        self.layout["log_area"].update(self.log_area)
        self.layout["status_bar"].update(self.status_bar)
        self.max_y = 0
        self.max_x = 0
        self.frame_buffer = ""
        self.status_bar_setter = status_bar_setter
        self.log_area_y = 0

        self.log_file = log_file
        self.print_lock = threading.Lock()
        self.print_buffer = ""
        self.buffer_handler_lock = threading.Lock()
        self.close_signal = False
        self.tui_thread = None

        self.server_close_event = server_close_event

    def get_index_which_wcswidth_less_than(self, string, width):
        index = 0
        sum_width = 0
        for i, c in enumerate(string):
            sum_width += wcw.wcwidth(c)
            if sum_width > width:
                break
            index = i
        return index

    def handle_print_buffer(self):
        # 处理print_buffer
        with self.print_lock:
            if self.print_buffer != "":
                self.frame_buffer += self.print_buffer
                self.print_buffer = ""

        if len(self.frame_buffer) > 150000:
            self.frame_buffer = self.frame_buffer[-125000:]

        # 将frame_buffer中的内容添加到log_buffer中
        max_width = self.max_x - 4
        lines = self.frame_buffer.splitlines(keepends=True)
        lines = [line.replace("\n", " ") for line in lines]
        last_len = len(self.log_buffer)
        tmp_buffer = []
        for line in lines:
            while len(line) > 0:
                index = self.get_index_which_wcswidth_less_than(line, max_width)
                tmp_buffer.append(line[:index + 1])
                line = line[index + 1:]
        self.log_buffer = tmp_buffer
        if self.log_index < 0:
            self.log_index -= len(self.log_buffer) - last_len
        self.log_index = max(min(self.log_index, 0), -len(self.log_buffer))

    def buffer_handler(self):
        while not self.close_signal:
            with self.buffer_handler_lock:
                self.handle_print_buffer()
            time.sleep(0.1)
        print("[Waring]Buffer handler closed")

    def run(self):
        threading.Thread(target=self.key_handler).start()
        buffer_thread = threading.Thread(target=self.buffer_handler)
        buffer_thread.start()
        with Live(self.layout, console=self.console, refresh_per_second=10) as live:
            while not self.close_signal:

                self.max_x, self.max_y = self.console.size
                # 显示日志
                log_text = ""
                # 显示日志区域
                self.log_area_y = self.max_y - 3
                line_idx = 0
                with self.buffer_handler_lock:
                    tmp_buffer = self.log_buffer.copy()
                    tmp_log_index = self.log_index

                for i in range(self.log_area_y):
                    # 计算日志索引(log_index-log_height+i)对应的日志在log_buffer中的索引
                    log_buffer_index = len(tmp_buffer) + tmp_log_index - self.log_area_y + i
                    if log_buffer_index < 0:
                        continue
                    if log_buffer_index >= len(tmp_buffer):
                        break
                    log_line = tmp_buffer[log_buffer_index]
                    log_text += log_line + "\n"
                    line_idx += 1

                self.log_area = Panel(Text(log_text), title="Log", width=self.max_x, height=self.max_y - 1,
                                      box=box.SQUARE, border_style="blue")

                # 显示状态条
                self.status_bar = self.status_bar_setter(self.max_x)

                self.layout["log_area"].update(self.log_area)
                self.layout["status_bar"].update(self.status_bar)

                live.update(self.layout)
                time.sleep(0.1)  # 降低CPU占用
            if self.close_signal:
                # 清空TUI
                live.update(Text("[Waring]TUI closed", style="red"))
                live.stop()
        buffer_thread.join()
        self.cleanup()
        if self.server_close_event is not None:
            self.server_close_event()

    def key_handler(self):
        def on_press(key):
            with self.buffer_handler_lock:
                if key == readchar.key.UP or key == 'w':  # 向上滚动
                    self.log_index = max(self.log_index - self.log_area_y // 3 - 1,
                                         -len(self.log_buffer) + self.log_area_y)
                elif key == readchar.key.DOWN or key == 's':  # 向下滚动
                    self.log_index = min(self.log_index + self.log_area_y // 3 - 1, 0)
                elif key == readchar.key.PAGE_UP:  # 向上翻页
                    self.log_index = max(self.log_index - self.log_area_y, -len(self.log_buffer) + self.log_area_y)
                elif key == readchar.key.PAGE_DOWN:  # 向下翻页
                    self.log_index = min(self.log_index + self.log_area_y, 0)
                elif key == readchar.key.SPACE:
                    self.log_index = 0

        while True:
            try:
                key = readchar.readkey()
                on_press(key)
            except KeyboardInterrupt:
                self.close_signal = True
                print("[Waring]Close signal received")
                break

    def print(self, *args, **kwargs):
        with self.print_lock:
            buffer = " ".join([str(x) for x in args])
            # 写入日志文件
            if self.log_file is not None:
                try:
                    self.log_file.write("[" + str(time.asctime()) + "]" + buffer[:4096] + "\n")
                    self.log_file.flush()
                except:
                    pass
            buffer = buffer[:4096]  # 限制输出长度
            self.print_buffer += buffer + "\n"
    def log(self, level, entity, *args, **kwargs):
        self.print(f"[{level}][{entity}]", *args, **kwargs)
    def clear(self):
        self.print_buffer = ""

    def cleanup(self):
        pass

    def __del__(self):
        self.cleanup()

    def run_TUI_thread(self):
        self.tui_thread = threading.Thread(target=self.run, args=())
        self.tui_thread.start()

    def stop_TUI_thread(self):
        if self.tui_thread is not None:
            self.close_signal = True
            self.tui_thread.join()

    def get_log_buffer(self):
        return self.log_buffer
    
    def get_frame_buffer(self):
        return self.frame_buffer
