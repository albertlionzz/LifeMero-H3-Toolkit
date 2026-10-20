# LifeMero × HUMAN 3.0 Toolkit

> 元类型标注 + 分龄切片 + 双通道匹配引擎 + UI 视觉稿，配套设计文档。
> 本仓库已初始化 git 并完成首次提交，拉到本地后只需添加远程并推送。

## 目录结构

```
LifeMero-H3-Toolkit/
├── LifeMero_HUMAN3_借鉴设计.md      # 总设计文档（4个功能 + 数据结构 + 路线图）
└── tools/
    ├── annotate_metatype.py         # 功能② 元类型批量标注（LLM + mock/续跑/复核报告）
    ├── phase_pipeline.py            # 功能① LifePhase 分龄生成（Δ偏移量方案）
    ├── simulate_blend.py            # 双通道混排算法模拟验证
    ├── persons_sample.json          # 10人示例数据集
    ├── ui_mockup.html               # UI 视觉稿（浏览器直接打开）
    └── lib/matching/
        └── metatype_engine.dart     # Flutter 双通道匹配引擎模块
```

## 快速开始

```bash
pip install requests

# 1) mock 验证数据格式（零成本）
python tools/annotate_metatype.py --input 你的数据.json --mock
python tools/phase_pipeline.py   --input persons_annotated.json --mock

# 2) 真实标注（DeepSeek 116人约几分钱）
set OPENAI_API_KEY=sk-xxx
set OPENAI_BASE_URL=https://api.deepseek.com/v1
python tools/annotate_metatype.py --input persons.json --model deepseek-chat
python tools/phase_pipeline.py   --input persons_annotated.json --model deepseek-chat
```

## 在笔记本上推送到远程仓库

### 方式一：PowerShell（推荐）

```powershell
cd LifeMero-H3-Toolkit
.\push_to_remote.ps1 -RemoteUrl https://github.com/你的用户名/LifeMero-H3-Toolkit.git
```

### 方式二：手动 git

```bash
cd LifeMero-H3-Toolkit
git remote add origin https://github.com/你的用户名/LifeMero-H3-Toolkit.git
git push -u origin master
```

> 远程仓库先在 GitHub/Gitee 网页上创建（**不要**勾选初始化 README，保持空仓库）。
> Gitee 示例：`https://gitee.com/你的用户名/lifemero-h3-toolkit.git`
> 推送时按提示登录即可（或配置 Personal Access Token）。

## 数据流水线

```
persons.json（你的116人数据集）
    ↓ annotate_metatype.py
persons_annotated.json（+元类型）→ review_report.md（人工复核🔴项）
    ↓ phase_pipeline.py
persons_phased.json（+分龄切片）→ phase_review.md（人工复核待确认项）
    ↓ 接入 Flutter 工程
metatype_engine.dart（双通道混排）+ ui_mockup.html 对应的 UI 组件
```
