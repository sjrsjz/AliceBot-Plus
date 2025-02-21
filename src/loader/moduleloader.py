import importlib
import os
import sys
from typing import Dict, Any, Optional
from pathlib import Path
#import logging

class ModuleLoader:
    """模块热重载器，用于动态加载和重载Python模块"""
    
    def __init__(self, module_dir: str):
        """
        初始化模块加载器
        
        Args:
            module_dir: 模块目录的路径
        """
        self.module_dir = Path(module_dir)
        self.modules: Dict[str, Any] = {}  # 模块缓存
        self.last_modified: Dict[str, float] = {}  # 文件最后修改时间
        #self.logger = logging.getLogger("ModuleLoader")
        self._watch_interval = 1.0  # 文件监视间隔(秒)

    def _get_module_path(self, module_name: str) -> Path:
        """获取模块文件的完整路径"""
        return self.module_dir / f"{module_name}.py"

    def _get_module_modified_time(self, module_path: Path) -> float:
        """获取模块文件的最后修改时间"""
        return os.path.getmtime(module_path)

    def load_module(self, module_name: str) -> Optional[Any]:
        """
        加载或重载一个模块
        
        Args:
            module_name: 模块名称（不含.py后缀）
            
        Returns:
            加载的模块对象，加载失败则返回None
        """
        try:
            module_path = self._get_module_path(module_name)
            
            if not module_path.exists():
                #self.logger.error(f"Module {module_name} not found at {module_path}")
                print(f"[🟥|ModuleLoader]Module {module_name} not found at {module_path}")
                return None

            current_mtime = self._get_module_modified_time(module_path)
            last_mtime = self.last_modified.get(module_name, 0)
            
            # 检查是否需要重新加载
            if module_name in self.modules and current_mtime <= last_mtime:
                return self.modules[module_name]
                
            # 创建唯一的模块名，确保每次重载都是新的副本
            unique_module_name = f"{module_name}_{current_mtime}"
            
            # 清理旧的模块引用
            if module_name in sys.modules:
                del sys.modules[module_name]
            if unique_module_name in sys.modules:
                del sys.modules[unique_module_name]
                
            # 重新加载模块
            spec = importlib.util.spec_from_file_location(unique_module_name, module_path)
            if spec is None:
                #self.logger.error(f"Failed to create module spec for {module_name}")
                print(f"[🟥|ModuleLoader]Failed to create module spec for {module_name}")
                return None
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[unique_module_name] = module  # 将模块添加到 sys.modules
            
            if spec.loader:
                spec.loader.exec_module(module)

            # 直接存储模块对象，不进行深拷贝
            self.modules[module_name] = module
            self.last_modified[module_name] = current_mtime
            
            action = "reloaded" if module_name in self.modules else "loaded"
            #self.logger.info(f"Successfully {action} module {module_name}")
            print(f"[🟩|ModuleLoader]Successfully {action} module {module_name}")
            
            return module

        except Exception as e:
            #self.logger.error(f"Error loading module {module_name}: {str(e)}")
            print(f"[🟥|ModuleLoader]Error loading module {module_name}: {str(e)}")
            return None
    def load_all_modules(self) -> Dict[str, Any]:
        """
        加载目录中的所有Python模块
        
        Returns:
            包含所有已加载模块的字典
        """
        loaded_modules = {}
        
        for file_path in self.module_dir.glob("*.py"):
            if file_path.stem.startswith("__"):
                continue
                
            module = self.load_module(file_path.stem)
            if module:
                loaded_modules[file_path.stem] = module
                
        return loaded_modules

    def unload_module(self, module_name: str) -> bool:
        """
        卸载一个模块
        
        Args:
            module_name: 要卸载的模块名称
            
        Returns:
            卸载是否成功
        """
        try:
            module_path = str(self._get_module_path(module_name).absolute())
            if module_path in sys.modules:
                del sys.modules[module_path]
            if module_name in self.modules:
                del self.modules[module_name]
            if module_name in self.last_modified:
                del self.last_modified[module_name]
            return True
        except Exception as e:
            #self.logger.error(f"Error unloading module {module_name}: {str(e)}")
            print(f"[🟥|ModuleLoader]Error unloading module {module_name}: {str(e)}")
            return False
        
    def unload_all_modules(self) -> bool:
        """
        卸载目录中的所有Python模块
        
        Returns:
            卸载是否成功
        """
        try:
            for module_name in list(self.modules.keys()):
                self.unload_module(module_name)
            return True
        except Exception as e:
            #self.logger.error(f"Error unloading all modules: {str(e)}")
            print(f"[🟥|ModuleLoader]Error unloading all modules: {str(e)}")
            return False

    def __del__(self):
        self.unload_all_modules()
        #self.logger.info("ModuleLoader destroyed")
        print("[🟧|ModuleLoader]ModuleLoader destroyed")

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unload_all_modules()
        #self.logger.info("ModuleLoader exited")
        print("[🟧|ModuleLoader]ModuleLoader exited")
        
    def from_path(self, subpath: str):
        """支持子路径导入"""
        new_path = Path(self.module_dir) / subpath
        return ModuleLoader(str(new_path))
        
    def import_module(self, name: str):
        """模拟 import 语法"""
        return self.load_module(name)