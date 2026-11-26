# Git 仓库接入体检

一个面向公开 GitHub 仓库的只读接入检查工具。用户只需输入仓库链接，即可查看接入就绪度评分、检测项目、主要风险及建议。

## 技术栈

- 前端：Vue 3、Vite、Lucide
- 后端：Python 3.10+ 标准库，无第三方 Python 运行依赖
- 仓库读取：GitHub 公开网页与原始文件地址，无需 API Token

## 功能与检查范围

- 检查根目录 README、常见依赖清单及 README 中的安装和启动说明。
- 尝试识别启动入口、`package.json` 常见运行脚本和 Windows 专用 `.bat`、`.cmd`、`.ps1`、`.vbs` 脚本。
- 检查疑似 Windows/macOS/Linux 用户目录的绝对路径。
- 检查已提交 `.env` 文件和常见 OpenAI 风格、AWS、Bearer、GitHub 令牌及私钥标记；报告只显示文件名和风险类型，不回显密钥内容。
- 展示评分、按级别筛选的风险清单、覆盖范围，并导出 JSON 报告。

评分是基于启发式规则的工程参考，不是安全审计结论，也不能证明仓库可运行。密钥规则可能误报或漏报；绝对路径只覆盖常见 Windows 用户/程序目录和 `/Users`、`/home`。当前未执行仓库代码，不运行安装脚本，不检查 Git 历史、子模块、Git LFS 二进制、被排除目录，也不运行构建、测试或漏洞扫描。

## 本地运行

需要 Python 3.10+、Node.js 20+ 和 npm。

```powershell
cd D:\load\智能体\git-repo-readiness
python -m unittest discover -s test -v
```

首次安装前端依赖并构建：

```powershell
cd D:\load\智能体\git-repo-readiness\frontend
npm install
npm run build
```

启动服务（从项目根目录执行）：

```powershell
cd D:\load\智能体\git-repo-readiness
python server.py
```

打开 <http://127.0.0.1:8000>。也可在开发时运行后端 `python server.py`，另开终端执行 `cd frontend; npm run dev`，访问 Vite 输出的本地地址。默认仅监听 `127.0.0.1`；如自行设置 `HOST` 对外开放，请先为服务部署身份验证和请求频率限制。

## 扫描限制与更新策略

- 只读取 GitHub 默认分支最多 6 个子目录和 20 个重点文本文件；单文件最多 120 KB。依赖清单、README、启动脚本和配置文件优先读取。大文件、二进制、常见构建产物及依赖目录会跳过。
- 未遍历目录、过大文件和无法读取文件都显示在报告覆盖范围中；不要将部分扫描理解为未发现风险。
- 不需要 GitHub Token。GitHub 公开网页或原始文件若暂时不可访问，页面会提示重试。
- 当前实现是手动扫描：每次打开仓库主页获取默认分支的完整 commit SHA，随后按该 SHA 读取目录和重点文件。页面显示短 SHA、分支、扫描时间，并链接到对应提交；导出的 JSON 保留完整 SHA。仓库更新后再次点击“开始体检”即可生成新报告，当前版本每次都会重新读取选中的文件。
- 更新跟踪设计（尚未实现）：定期读取默认分支 HEAD SHA。若与上次报告相同，直接复用该 commit 的报告；若变化，比较两次 commit 的文件列表，按文件内容 SHA 缓存检测结果，只重扫新增、修改及新进入重点文件集合的文件，并移除已删除文件的结果，最后重新汇总评分和风险。这样不会对未变化文件重复做内容分析。
- 失败或访问受限的兜底设计（尚未实现）：保留最近一次成功报告但显著标注“旧结果”，显示其 commit、扫描时间和失败原因，提供手动重试；绝不把旧评分当作当前 commit 的结果。当前 demo 遇到错误会清除旧报告并显示错误提示，不生成新评分。
- 接入建议以每次提交或发布时重新扫描为准。评分阈值：85–100 较好，60–84 需完善，0–59 暂不建议接入。不同文件和规则产生的分数扣减可能重叠。

## GitHub 仓库发布

先在 GitHub 创建公开空仓库，再在本目录添加 remote 并推送：

```powershell
git init
git add .
git commit -m "feat: build Git repository readiness checker"
git branch -M main
git remote add origin https://github.com/<your-account>/git-repo-readiness.git
git push -u origin main
```

## 项目结构

```text
frontend/       Vue 3 页面和 Vite 构建配置
scanner.py      GitHub 读取、启发式分析和评分
server.py       Python HTTP API 与静态文件服务
test/           Python 标准库单元测试
AI_USAGE.md     AI 辅助开发记录与人工核验说明
```
