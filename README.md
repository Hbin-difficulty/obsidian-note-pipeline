# obsidian-note-pipeline

> 把任意文档（PDF / Word / TXT / 已有 Markdown）转成经过加工的 Obsidian 风格 Markdown 笔记 —— 先识别类型，再转换（图片内嵌），最后套用 vault 的 `AGENTS.md` / `PRD.md` 处理流程。

## 这是什么

一个 **WorkBuddy (CodeBuddy) Skill**，用于把一份原始文档加工成符合你笔记库规范的 Markdown 笔记。核心原则：

**先判断文件类型 → 若是 `.md` 直接处理；否则先转成 Markdown（图片以 base64 内嵌），再处理。**

## 支持格式

| 扩展名 | 处理方式 |
|--------|----------|
| `.md`  | 直接处理，不转换 |
| `.pdf` | PyMuPDF 转换（相对字号分层、Menlo 代码块识别、图片 base64 内嵌） |
| `.docx`| 纯标准库（zipfile + xml）转换，零额外依赖 |
| `.txt` | 轻量包裹为 Markdown 后处理 |
| 其他   | 停止并提示格式不支持 |

## 安装 / 使用

作为 WorkBuddy **用户级 Skill**，放到：

```
~/.workbuddy/skills/obsidian-note-pipeline/
```

然后在对话中说：

- “把 `xxx.pdf` 转成 md 笔记并处理”
- “处理一下这篇 `debug_纠错.md`”

Skill 会自动：检测类型 → 转换（如需要）→ 套用 `AGENTS.md` / `PRD.md`（frontmatter、AI 摘要、概念双链、AI 疑问、状态字段）。

## 命令行

所有脚本用隔离 venv 的 Python 运行（PyMuPDF 已装在该环境）：

```bash
PY="C:/Users/Lenovo/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY scripts/run_pipeline.py "path/to/file.pdf" \
  --title "项目开发流程" \
  --tags "AI,编程,教程,方法论,效率" \
  --summary-text "..." \
  --concepts "提示词,回滚,类型安全" \
  --doubts-text "..." \
  --out "vibe_conding学习及使用技巧/项目开发流程.md"
```

对已有的 `.md` 笔记直接处理（跳过转换）：

```bash
$PY scripts/run_pipeline.py "debug_纠错.md" --summary-text "..." --concepts "..."
```

## 工作原理

1. **检测类型**（按扩展名分流，见上表）。
2. **转换**（`.md` 跳过）：PDF 用相对字号定标题层级、Menlo 字体定代码块、图片 base64 内嵌；DOCX 用纯标准库解析标题 / 列表 / 表格 / 代码 / 内嵌图。
3. **生成判断内容**（由 Agent 完成）：标题、白名单标签、AI 摘要、概念词表、AI 疑问。
4. **处理**：写入 frontmatter、插入 `## 📝 AI摘要`、注入概念双链（避让代码块）、文末加 AI 疑问注释、更新状态字段。

## 目录结构

```
obslidian-note-pipeline/
├── SKILL.md                      # Skill 定义与工作流
├── README.md                     # 本文件
├── scripts/
│   ├── run_pipeline.py           # 入口：检测 → 转换 → 处理
│   ├── convert_pdf.py            # PDF → MD（PyMuPDF）
│   ├── convert_docx.py           # DOCX → MD（stdlib）
│   └── process_note.py           # AGENTS/PRD 处理
└── references/
    └── conversion_notes.md       # 转换踩坑记录
```

## 已知局限

- PDF 中“列表序号、行内引号”常被渲染成图形而非文字，提取后可能丢失——会如实告知，而非编造。
- “概念建链”模式下插入的双链可能指向尚未创建的笔记（Obsidian 点击即新建）；若你的 vault 要求只链已存在笔记，请先确认。

## License

MIT
