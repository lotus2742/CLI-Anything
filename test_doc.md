# CLI-Anything 是什么

CLI-Anything 是一个开源项目，目标是把任何桌面软件变成 AI Agent 可以调用的 CLI 工具。

---

# 为什么需要它

AI Agent 只能调用 API，但大量有用的软件没有 API。

CLI-Anything 填补了这个空白：给每个软件套上标准 CLI 壳，Agent 就能像调用函数一样操控软件。

---

# doc2video 能做什么

doc2video 是 CLI-Anything 生态中的一个新 harness。

输入一篇文档，输出一个带配音的 MP4 视频。整个流程全自动，不需要手动操作任何软件。

---

# 技术实现

流水线分四步：

第一步，解析文档，把 Markdown 或 PDF 拆成一页一页的幻灯片。

第二步，用 edge-tts 生成语音，免费，支持中英日等 100 多种声音。

第三步，用 Pillow 把每张幻灯片渲染成图片帧序列。

第四步，用 ffmpeg 把图片帧和音频合并成最终的 MP4 文件。

---

# 总结

文档进，视频出。一行命令搞定。
