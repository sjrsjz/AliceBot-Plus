<div align="center">
  <h1><img src="image/readme/1740150452111.jpg" width="28px" height="auto" alt="AliceBot Logo" style="vertical-align: middle;"> AliceBot+</h1>
  <p>
    <strong>QQ bot powered by AI</strong>
  </p>
</div>

---

#### **AliceBot+** 是一个基于 OneBot v11 标准的 QQ 机器人，基于非开源的原始版本重构而来，目的是为了提供更清晰的代码结构和更好的可维护性。同时提供插件系统，方便用户自定义功能。

## 🔧功能
- [x] 通过 **OneBot v11** 标准接收和发送消息
- [x] NapCatQQ Websocket API支持
- [x] 多种消息类型
- [x] 群聊消息处理
- [x] 自身局部代码热重载
- [x] 高度可扩展定制化AI提示词模板
- [x] AI 格式化富文本输出，CoT推理
- [x] 文档渲染器 (支持 Markdown/HTML/LaTeX/Typst，基于无头浏览器)
- [x] 网页搜索、读取解析
- [ ] 插件系统 (仍未完成迁移)
- [ ] 上下文管理器 (仍未完成迁移)
- [ ] AI 模型支持 (仍未完成迁移)
- [ ] 复杂指令解析 (仍未完成迁移)
- [ ] 私聊消息处理 

## 🚀快速开始
由于项目采用 Python 包的方式进行源代码组织，因此建议使用以下方式进行运行：

```bash
# 克隆项目
git clone https://github.com/sjrsjz/AliceBot-Plus
# 进入项目目录
cd AliceBot-Plus
# 安装依赖
pip install -r requirements.txt
# 运行
python -m alicebot
```


## 📜 开源许可
本项目采用 [MIT](LICENSE) 开源许可证。