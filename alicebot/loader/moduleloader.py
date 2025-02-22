import importlib
import os
import sys
from typing import Dict, Any, Optional, Set
from pathlib import Path
import threading
import time


# import logging

class ModuleLoader:
    """模块热重载器，用于动态加载和重载Python模块"""

    def __init__(self, module_dir: str, log_func=print):
        """
        初始化模块加载器
        
        Args:
            module_dir: 模块目录的路径
        """
        self.module_dir = Path(module_dir)
        self.instances: Dict[str, Dict[str, Any]] = {}
        self.last_modified: Dict[str, float] = {}
        self._watch_interval = 1.0
        self._caller_id = id(self)
        self._watch_thread: Optional[threading.Thread] = None
        self._should_stop = threading.Event()
        self._hot_reload_modules: Set[str] = set()  # 存储需要热重载的模块名称
        self._lock = threading.Lock()  # 添加线程锁
        self._lock_2 = threading.Lock()  # 添加线程锁
        self._log_func = log_func
        self.kwargs = {}

    def _get_module_path(self, module_name: str) -> Path:
        """获取模块文件的完整路径"""
        return self.module_dir / f"{module_name}.py"

    def _get_module_modified_time(self, module_path: Path) -> float:
        """获取模块文件的最后修改时间"""
        return os.path.getmtime(module_path)

    def _watch_for_changes(self):
        """监控文件变化的线程函数"""
        while not self._should_stop.is_set():
            with self._lock:
                for module_name in self._hot_reload_modules:
                    try:
                        module_path = self._get_module_path(module_name)
                        if not module_path.exists():
                            continue

                        current_mtime = self._get_module_modified_time(module_path)
                        if (module_name in self.last_modified and
                                current_mtime > self.last_modified[module_name]):
                            self._log_func(f"[🟨|ModuleLoader]Detected change in module {module_name}, reloading...",
                                           flush=True)
                            self.load_module(module_name, hot_reload=True, **self.kwargs)
                    except Exception as e:
                        self._log_func(f"[🟥|ModuleLoader]Error checking module {module_name}: {str(e)}")

            time.sleep(self._watch_interval)

    def start_watching(self):
        """启动文件监控线程"""
        if self._watch_thread is None or not self._watch_thread.is_alive():
            self._should_stop.clear()
            self._watch_thread = threading.Thread(target=self._watch_for_changes, daemon=True)
            self._watch_thread.start()
            self._log_func("[🟩|ModuleLoader]Started watching for module changes")

    def stop_watching(self):
        """停止文件监控线程"""
        if self._watch_thread and self._watch_thread.is_alive():
            self._should_stop.set()
            self._watch_thread.join()
            self._log_func("[🟧|ModuleLoader]Stopped watching for module changes")

    def load_module(self, module_name: str, hot_reload: bool = False, use_lock=False, **kwargs) -> Optional[Any]:
        """加载或重载一个模块"""
        self.kwargs = kwargs
        with self._lock if use_lock else self._lock_2:
            try:
                module_path = self._get_module_path(module_name)

                if not module_path.exists():
                    self._log_func(f"[🟥|ModuleLoader]Module {module_name} not found at {module_path}")
                    return None

                if hot_reload:
                    self._hot_reload_modules.add(module_name)
                    if not self._watch_thread or not self._watch_thread.is_alive():
                        self.start_watching()
                current_mtime = self._get_module_modified_time(module_path)
                caller_id = str(id(self))  # 获取当前调用者的ID

                # 清理所有相关的模块缓存
                for key in list(sys.modules.keys()):
                    if module_name in key:
                        del sys.modules[key]

                # 如果之前存在实例，先清理
                if caller_id in self.instances and module_name in self.instances[caller_id]:
                    del self.instances[caller_id][module_name]

                # 为每个调用者创建独立的模块实例字典
                if caller_id not in self.instances:
                    self.instances[caller_id] = {}

                # 重新加载模块
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None:
                    self._log_func(f"[🟥|ModuleLoader]Failed to create module spec for {module_name}")
                    return None

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module

                for key, value in kwargs.items():
                    setattr(module, key, value)

                if spec.loader:
                    spec.loader.exec_module(module)

                # 存储该调用者的模块实例
                self.instances[caller_id][module_name] = module
                self.last_modified[module_name] = current_mtime

                action = "reloaded" if module_name in self.instances[caller_id] else "loaded"
                self._log_func(f"[🟩|ModuleLoader]Successfully {action} module {module_name} for caller {caller_id}",
                               flush=True)

                if hasattr(module, "on_load"):
                    self._log_func(f"[🟩|ModuleLoader]Calling on_load for module {module_name}")
                    module.on_load(**kwargs)

                return module

            except Exception as e:
                self._log_func(f"[🟥|ModuleLoader]Error loading module {module_name}: {str(e)}")
                return None

    def get_module(self, module_name: str) -> Optional[Any]:
        """动态获取一个模块"""
        caller_id = str(id(self))
        if caller_id in self.instances and module_name in self.instances[caller_id]:
            return self.instances[caller_id][module_name]
        return None
    
    def get_all_modules(self) -> Dict[str, Any]:
        """获取所有模块"""
        caller_id = str(id(self))
        return self.instances.get(caller_id, {})

    def __getitem__(self, module_name: str) -> Optional[Any]:
        return self.get_module(module_name)

    def unload_module(self, module_name: str) -> bool:
        """卸载一个模块"""
        with self._lock:
            try:
                caller_id = str(id(self))
                if caller_id in self.instances and module_name in self.instances[caller_id]:
                    del self.instances[caller_id][module_name]
                if module_name in self.last_modified:
                    del self.last_modified[module_name]
                self._hot_reload_modules.discard(module_name)  # 移除热重载监控
                return True
            except Exception as e:
                self._log_func(f"[🟥|ModuleLoader]Error unloading module {module_name}: {str(e)}")
                return False

    def unload_all_modules(self) -> bool:
        """卸载所有模块"""
        try:
            caller_id = str(id(self))
            if caller_id in self.instances:
                self.instances[caller_id].clear()
            return True
        except Exception as e:
            self._log_func(f"[🟥|ModuleLoader]Error unloading all modules: {str(e)}")
            return False

    def __del__(self):
        self.stop_watching()
        self.unload_all_modules()
        self._log_func("[🟧|ModuleLoader]ModuleLoader destroyed")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_watching()
        self.unload_all_modules()
        self._log_func("[🟧|ModuleLoader]ModuleLoader exited")

    def __enter__(self):
        return self

    def from_path(self, subpath: str):
        """支持子路径导入"""
        new_path = Path(self.module_dir) / subpath
        return ModuleLoader(str(new_path))

    def import_module(self, name: str):
        """模拟 import 语法"""
        return self.load_module(name)
