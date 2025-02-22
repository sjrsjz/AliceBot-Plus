import fJson as fjson
import os

__key_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
__key_path = os.path.join(__key_dir, "apikey.json")


@fjson.DataClass
class ApiKey:
    def __init__(self):
        self.gemini = []
        self.gemini_index = 0

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


if not os.path.exists(__key_dir):
    os.makedirs(__key_dir)
if not os.path.exists(__key_path):
    config = ApiKey()
    config.save(__key_path)

config = ApiKey.load(__key_path)
