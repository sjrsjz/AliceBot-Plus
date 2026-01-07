import fJson as fjson
import os

__key_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
__key_path = os.path.join(__key_dir, "apikey.json")


@fjson.DataClass
class ApiKey:
    def __init__(self):
        self.gemini = []
        self.gemini_index = 0
        self.siliconflow = []
        self.siliconflow_index = 0
        self.openai_hk = []
        self.openai_hk_index = 0
        self.deepseek = []
        self.deepseek_index = 0
        self.yunwuapi = []
        self.yunwuapi_index = 0
        self.bolatuapi = []
        self.bolatuapi_index = 0

    def save(self, path: str):
        """保存配置到文件"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.json(indent=4, multi_line=True))

    @classmethod
    def load(cls, path: str):
        """从文件加载配置"""
        if not os.path.exists(path):
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = fjson.decode(f.read())
                config = cls()
                if data:
                    config.gemini = data.get("gemini", [])
                    config.gemini_index = data.get("gemini_index", 0)
                    config.siliconflow = data.get("siliconflow", [])
                    config.siliconflow_index = data.get("siliconflow_index", 0)
                    config.openai_hk = data.get("openai_hk", [])
                    config.openai_hk_index = data.get("openai_hk_index", 0)
                    config.deepseek = data.get("deepseek", [])
                    config.deepseek_index = data.get("deepseek_index", 0)
                    config.yunwuapi = data.get("yunwuapi", [])
                    config.yunwuapi_index = data.get("yunwuapi_index", 0)
                    config.bolatuapi = data.get("bolatuapi", [])
                    config.bolatuapi_index = data.get("bolatuapi_index", 0)
                return config
        except Exception as e:
            print(f"[ApiKey] Failed to load config: {e}")
            return cls()

    def key_gemini(self):
        if not self.gemini:
            return None
        key = self.gemini[self.gemini_index]
        self.gemini_index = (self.gemini_index + 1) % len(self.gemini)
        return key

    def key_siliconflow(self):
        if not self.siliconflow:
            return None
        key = self.siliconflow[self.siliconflow_index]
        self.siliconflow_index = (self.siliconflow_index + 1) % len(self.siliconflow)
        return key

    def key_openai_hk(self):
        if not self.openai_hk:
            return None
        key = self.openai_hk[self.openai_hk_index]
        self.openai_hk_index = (self.openai_hk_index + 1) % len(self.openai_hk)
        return key
    
    def key_deepseek(self):
        if not self.deepseek:
            return None
        key = self.deepseek[self.deepseek_index]
        self.deepseek_index = (self.deepseek_index + 1) % len(self.deepseek)
        return key
    
    def key_yunwuapi(self):
        if not self.yunwuapi:
            return None
        key = self.yunwuapi[self.yunwuapi_index]
        self.yunwuapi_index = (self.yunwuapi_index + 1) % len(self.yunwuapi)
        return key

    def key_bolatu(self):
        if not self.bolatuapi:
            return None
        key = self.bolatuapi[self.bolatuapi_index]
        self.bolatuapi_index = (self.bolatuapi_index + 1) % len(self.bolatuapi)
        return key

if not os.path.exists(__key_dir):
    os.makedirs(__key_dir)
if not os.path.exists(__key_path):
    config = ApiKey()
    config.save(__key_path)

config = ApiKey.load(__key_path)
