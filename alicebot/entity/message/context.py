import copy
class ContextManager:
    def __init__(self, context = []):
        self.context = context

    def push_message(self, message):
        self.context.append(copy.deepcopy(message))

    def pop_message(self):
        self.context.pop()

    def get_message(self):
        return self.context

    def set_message(self, message):
        self.context = copy.deepcopy(message)

    def clear(self):
        self.context = []

    def get_last_message(self):
        return self.context[-1]

    def withdraw(self):
        # 回退到上一个assistant消息
        if len(self.context) > 0:
            if self.context[-1]["role"] == "assistant":
                self.context.pop()
            while len(self.context) > 0 and self.context[-1]["role"] == "user":
                self.context.pop()


class StreamContextManager:
    def __init__(self, context = [], max_length=50):
        self.context = context
        self.max_length = max_length
        self.vectorize_callback = None  # 批量向量化回调函数
        self.group_id = None  # 群组ID，用于向量化

    def set_vectorize_callback(self, callback, group_id):
        """
        设置向量化回调函数
        
        Args:
            callback: 批量向量化函数，接收参数 (group_id, messages)
            group_id: 群组ID
        """
        self.vectorize_callback = callback
        self.group_id = group_id

    async def push_message(self, message):
        self.context.append(copy.deepcopy(message))

        # 当缓冲池超过最大容量50的1.5倍时，批量向量化最早的一半
        if len(self.context) >= self.max_length + (self.max_length // 2):
            messages_to_vectorize = self.context[:self.max_length // 2]

            # 如果设置了向量化回调，执行批量向量化
            if self.vectorize_callback and self.group_id:
                try:
                    await self.vectorize_callback(self.group_id, messages_to_vectorize)
                except Exception as e:
                    # 向量化失败不应影响主流程
                    print(f"[ERROR] Vectorization callback failed: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[WARN] Vectorization skipped: callback={self.vectorize_callback}, group_id={self.group_id}")

            self.context = self.context[self.max_length // 2 :]

    def get_message(self):
        return self.context

    def clear(self):
        self.context = []

    def set_message(self, message):
        self.context = message
        if len(self.context) > self.max_length:
            self.context = self.context[-self.max_length:]
