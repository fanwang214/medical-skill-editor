# Medical Skill Editor

一个面向医生的可视化 Markdown 管理工具，用来维护医疗多智能体项目里的 `Skill` 和 `Prompt` 文档。医生不需要直接写 Markdown，可以在网页里编辑可读栏目；系统会保存版本记录，并生成对应的 `.md` 文件。

## 功能

- 管理多个 `Skill`
- 管理多个 `Prompt`
- 可视化编辑章节内容
- 保存修改人、版本备注和历史版本
- 查看当前内容与历史版本的修改对比
- 恢复历史版本
- 删除某个 Skill 或 Prompt
- 自动生成 Markdown 文件

## 文档类型

### Skill

Skill 是疾病、检查、诊断规则等长期知识文档。保存后生成：

```text
generated-skills/<skill-name>/SKILL.md
```

### Prompt

Prompt 是和 Agent 调用相关的提示词文档，例如“你是诊断医生 Agent，负责……”。保存后生成：

```text
generated-prompts/<prompt-name>/PROMPT.md
```

Prompt 和 Skill 是并列文档，不放在 Skill 章节里。

## 启动

在项目目录运行：

```bash
HOST=0.0.0.0 PORT=5173 python3 server.py
```

本机访问：

```text
http://127.0.0.1:5173/
```

局域网内医生访问：

```text
http://<你的局域网 IP>:5173/
```

例如：

```text
http://192.168.1.101:5173/
```

医生打开网页后可以直接修改并点击“保存版本”。保存后，你刷新网页即可看到同步后的内容。

## 数据保存在哪里

运行后会产生本地数据库：

```text
data/skills.db
```

数据库保存：

- Skill 当前内容
- Prompt 当前内容
- 修改人
- 版本备注
- 历史版本

`data/*.db` 已被 `.gitignore` 忽略，不会提交到 GitHub。

生成的 Markdown 文件保存在：

```text
generated-skills/
generated-prompts/
```

这两个目录可以提交到 GitHub，用于同步最终生成的文档。

## 医生修改后如何同步到 GitHub

医生在网页里保存后，后端会更新数据库，并重新生成 `generated-skills/` 或 `generated-prompts/` 下的 Markdown 文件。

要把这些新生成的文件同步到 GitHub，需要在本机提交并推送：

```bash
git status
git add generated-skills generated-prompts
git commit -m "Update generated medical documents"
git push
```

如果同时修改了前端或后端源码，也一起提交：

```bash
git add .
git commit -m "Update editor"
git push
```

后续可以再加一个“发布到 GitHub”按钮，让后端自动执行提交和推送；当前版本采用手动 Git 同步，更安全，也方便先确认医生改了什么。

## 测试

运行前端生成逻辑测试：

```bash
node --test skill.test.mjs
```

运行后端测试：

```bash
python3 -m unittest server_test.py
```

语法检查：

```bash
node --check app.js
node --check skill.js
python3 -m py_compile server.py
```

## 项目结构

```text
.
├── index.html
├── styles.css
├── app.js
├── skill.js
├── server.py
├── skill.test.mjs
├── server_test.py
├── generated-skills/
├── generated-prompts/
└── data/              # 本地数据库目录，不提交
```

## 注意

- 这个工具用于维护辅助诊断系统的知识和提示词文档，不替代医生诊断。
- 如果医生不在同一个局域网，需要部署到服务器或使用内网穿透。
- 多人同时编辑时，后端会用版本号避免旧页面覆盖新修改。
