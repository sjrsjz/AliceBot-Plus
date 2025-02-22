class ContextManager:
    def __init__(self):
        self.context = []

    def push_message(self, message):
        self.context.append(message)

    def pop_message(self):
        self.context.pop()

    def get_message(self):
        return self.context

    def set_message(self, message):
        self.context = message

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
    def __init__(self, max_length=50):
        self.context = []
        self.max_length = max_length

    def push_message(self, message):
        self.context.append(message)
        if len(self.context) > self.max_length:
            self.context.pop(0)

    def get_message(self):
        return self.context

    def clear(self):
        self.context = []

    def set_message(self, message):
        self.context = message
        if len(self.context) > self.max_length:
            self.context = self.context[-self.max_length:]
