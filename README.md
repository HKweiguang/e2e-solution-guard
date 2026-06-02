# e2e-solution-guard

> 让 AI 从"拍脑袋写文档"变成"按规矩做工程"。

一站式控制 AI 从想法到代码的全链路产物——PRD、交互设计、UI 原型、技术方案、测试报告。任何变更必须追溯上游、同步下游，防止 AI 幻觉与规则绕过。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 这解决什么问题？

用 AI 写方案时，这些场景是不是经常发生：

| 痛点 | 后果 |
|------|------|
| AI 凭空加了一个字段，但 PRD 里根本没定义 | 代码和文档对不上，联调时才发现 |
| 改了 PRD 的需求，忘了同步技术方案和测试用例 | 产物之间逐渐分裂，各自为政 |
| 跨会话后 AI 不记得之前的约束，规则被悄悄绕过 | 每次都要重新交代上下文 |

**e2e-solution-guard 用"产物依赖网络"锁死这些漏洞**：每份产物头部声明上游来源，变更必须双向追溯，AI 脑补的内容会被审计脚本拦下。

---

## 怎么工作？

### 1. 产物互相引用，形成依赖网络

```
PRD ──► 交互设计 ──► UI 原型 ──► 测试报告
  │         │           │
  └─────────┴───────────┘
            │
            ▼
      技术方案（按服务聚合）
```

每份产物文件开头都有一个**上游文档**表格，写明"我依赖谁、引用了哪些内容"。

### 2. 变更双向锁死

| 你做了什么 | AI 必须怎么做 |
|-----------|-------------|
| **修改上游**（如 PRD） | 扫描所有下游产物，询问是否同步；用户拒绝则标注 `[待同步]` |
| **修改下游**（如技术方案） | 逐条比对是否超出上游定义，超出则**立即停止**，先改上游 |

### 3. 自动审计兜底

```bash
# 单产物审计（传入直接上游 + 项目顶层定义）
python3 scripts/doc-audit.py docs/需求/PRD-订单.md --type prd \
  --upstream docs/需求/PRD-顶层定义.md \
  --top-level docs/顶层定义/PRD-顶层定义.md

# 修改 PRD 后，扫描哪些下游需要同步
python3 scripts/doc-audit.py docs/需求/{PRD标题}.md --scan-downstream ./docs/

# 运行规则引擎冒烟测试（29 条用例 + 5 个模板验证）
make test
```

> **脚本与 AI 的分工**：`doc-audit.py` 负责结构化、确定性检查（格式、存在性、计数、连续性），覆盖约 73% 的机械检查项；语义判断（映射正确性、设计合理性）由 AI 负责。详见 `references/workflow/audit-procedure.md`。

---

## 快速开始

### 安装

```bash
# 方法1：用户级 skills（任意项目可用）
git clone https://github.com/YOUR_USERNAME/e2e-solution-guard.git ~/.config/agents/skills/e2e-solution-guard

# 方法2：项目级 skills（仅当前项目可用）
git clone https://github.com/YOUR_USERNAME/e2e-solution-guard.git .kimi/skills/e2e-solution-guard
```

### 第一次使用

```sh
/skill:e2e-solution-guard 帮我评估这个订单模块的想法
```

AI 会按以下流程执行：

1. **评估** → 分析可行性、识别与现有方案的冲突、明确缺失信息
2. **生成 PRD** → 按模板输出，头部自动写入上游依赖
3. **生成交互/UI** → 基于 PRD 逐层推导，不脑补额外功能
4. **生成技术方案** → 通过「功能点编号」与 PRD 建立多对多映射
5. **审计** → 运行 `doc-audit.py` 检查一致性

修改任何产物时，AI 会自动检查上下游影响，拒绝擅自越界。

---

## 产物组织方式

### 推荐目录结构

```
docs/
├── 顶层定义/                      # 全局规范（术语、状态值、编码规则）
│   └── ...
├── 需求/                          # PRD 按业务模块聚合
│   ├── {PRD 标题}.md
│   └── ...
├── 交互设计/                      # 按业务端聚合（推荐）
│   ├── 消费者/
│   │   └── {交互设计标题}.md
│   └── 商家/
│       └── {交互设计标题}.md
├── UI/                            # 按业务端+设备聚合（推荐）
│   ├── 消费者-web/
│   │   └── {UI 标题}.html
│   └── 消费者-app/
│       └── {UI 标题}.html
├── 测试/                          # 按模块聚合
│   └── {测试报告标题}.md
└── 技术/                          # 按服务聚合
    ├── {服务A 技术方案}.md
    └── {服务B 技术方案}.md
```

### 关键设计

| 产物 | 聚合单位 | 原因 |
|------|---------|------|
| PRD、测试报告 | **按业务模块** | 同一模块的需求和验证放在一起 |
| 交互设计 | **按业务端** | 同一业务端的交互体验是连贯的，跨模块 |
| UI | **按业务端+设备** | 同一业务端+设备的视觉风格一致，跨模块 |
| 技术方案 | **按服务/技术边界** | 技术方案的边界是代码的物理边界 |

**PRD ↔ 技术方案是多对多映射**：通过「功能点编号」关联。一个功能可能涉及多个服务，一个服务也可能支撑多个功能。

> 详细目录结构、编号规范、多业务端组织方式参见 [`references/workflow/product-organization.md`](references/workflow/product-organization.md)

---

## 核心概念

### 上游依赖声明

每份产物开头必须包含：

```markdown
**上游文档**：

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| PRD-v1-订单模块 | 需求输入 | ORDER-DEFAULT-001 – ORDER-DEFAULT-006 |
| 项目技术-顶层定义 | 规范继承 | 技术栈、接口约定 |
```

### 脚本与 AI 的分工

| 维度 | 脚本 (`doc-audit.py`) | AI |
|------|----------------------|--------------|
| 负责范围 | 格式、存在性、计数、连续性 | 语义、正确性、合理性 |
| 判断依据 | 模式/规则/穷举 | 业务上下文理解 |
| 结果类型 | 通过/不通过（确定性） | 通过/不通过/存疑 |
| 当前覆盖 | ~73% 的 `[脚本]` 检查项 | 100% 的 `[模型]` 检查项 + 剩余 27% `[脚本]` |

### 编号规范

所有产物统一使用 `{前缀}-{模块缩写}-{业务端标识}-{序号}` 格式，天生支持多业务端扩展：

| 产物 | 格式 | 单业务端示例 | 多业务端示例 |
|------|------|-------------|-------------|
| 功能编号 | `{模块}-{业务端}-{序号}` | `USER-DEFAULT-001` | `USER-CONSUMER-001` |
| 页面编号 | `PAGE-{业务端}-{平台}-{页面名}-{序号}` | `PAGE-DEFAULT-WEB-HOME-001` | `PAGE-CONSUMER-WEB-HOME-001` |
| 接口编号 | `{模块}-{业务端}-API-{序号}` | `ORDER-DEFAULT-API-001` | `ORDER-CONSUMER-API-001` |
| 用例编号 | `TC-{模块}-{业务端}-{序号}` | `TC-ORDER-DEFAULT-001` | `TC-ORDER-CONSUMER-001` |

> **业务端不是设备端**：业务端指使用系统功能的业务群体（消费者端、运营端、管理端），设备端（WEB/APP/MP）在页面编号中叫"平台"。单业务端项目固定为 `DEFAULT`。

多业务端项目：
- **PRD**：一个模块一份，内部按业务端分章节；用户故事和用户旅程按业务端分表展示
- **交互设计**：按业务端分文件
- **UI**：按业务端+设备分文件

---

## 项目结构

```
e2e-solution-guard/
├── SKILL.md                         # AI 指令手册（核心逻辑）
├── README.md                        # 本文件
├── LICENSE                          # MIT
├── references/
│   ├── steps/                       # 产物模板
│   │   ├── prd-step.md              # PRD 模板
│   │   ├── interaction-step.md      # 交互设计模板
│   │   ├── ui-step.md               # UI 原型模板（HTML）
│   │   ├── tech-step.md             # 技术方案模板
│   │   ├── test-step.md             # 测试报告模板
│   │   └── code-audit-report.md     # 代码审计报告模板
│   ├── top-level/                   # 顶层定义模板
│   │   ├── prd-top-level-template.md
│   │   ├── interaction-top-level-template.md
│   │   ├── ui-top-level-template.md
│   │   └── tech-top-level-template.md
│   ├── examples/                    # 填写示例与常见陷阱
│   │   ├── prd-examples.md
│   │   ├── interaction-examples.md
│   │   ├── tech-examples.md
│   │   └── test-examples.md
│   └── workflow/                    # 执行流程
│       ├── idea-evaluation.md       # 想法评估
│       ├── document-workflow.md     # 产物生成/修改
│       ├── change-propagation.md    # 变更传播
│       ├── code-verification.md     # 代码验证
│       ├── audit-procedure.md       # 审计策略
│       └── product-organization.md  # 产物组织与编号规范
└── scripts/
    ├── doc-audit.py                 # 一致性审计脚本（标准库 only）
    └── dev/
        ├── test_doc_audit.py        # 规则引擎冒烟测试（29 条用例）
        └── run-tests.sh             # 测试入口（冒烟测试 + 模板验证）
```

---

## 兼容性

- [Kimi Code CLI](https://github.com/MoonshotAI/kimi-cli)
- [Claude Code](https://github.com/anthropics/claude-code)
- [OpenAI Codex](https://github.com/openai/codex)

符合 [Agent Skills 开放格式](https://agentskills.io/)。

## License

[MIT](LICENSE)
