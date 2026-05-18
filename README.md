# e2e-solution-guard

一站式控制 AI 变更边界的产物依赖网络——从 PRD 到交互到 UI 到技术方案再到代码，任何变更必须追溯上游、同步下游，防止幻觉与规则绕过。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 是什么

`e2e-solution-guard` 是一个 [Kimi Code CLI](https://github.com/MoonshotAI/kimi-cli) / [Claude Code](https://github.com/anthropics/claude-code) / [Codex](https://github.com/openai/codex) 兼容的 **Agent Skill**。

它的核心不是"文档模板"，而是**一站式的边界控制系统**：

- 每份产物头部声明上游来源（`upstream-document`）
- 修改上游必须同步下游，或标注 `[待同步]`
- 修改下游不得超出上游定义
- AI 生成内容前必须做 gap 分析，禁止脑补

## 为什么

AI 辅助开发时，以下场景频繁出现：

1. **幻觉**：AI 凭空添加未定义的功能点、字段、接口
2. **脱节**：改了 PRD 却忘了同步技术方案，导致产物之间不一致
3. **上下文碎片化**：跨会话后 AI 不记得之前的约束，规则被悄悄绕过

`e2e-solution-guard` 通过**产物依赖网络**和**可运行的审计脚本**，一站式把 AI 从产物生成到代码落地锁死在既定边界内。

## 安装

将本仓库克隆到 Kimi CLI 的 skills 目录：

```bash
# 方法1：克隆到用户级 skills 目录（任意项目可用）
git clone https://github.com/YOUR_USERNAME/e2e-solution-guard.git ~/.config/agents/skills/e2e-solution-guard

# 方法2：克隆到项目级 skills 目录（仅当前项目可用）
git clone https://github.com/YOUR_USERNAME/e2e-solution-guard.git .kimi/skills/e2e-solution-guard
```

## 使用

在 Kimi CLI 中输入：

```sh
/skill:e2e-solution-guard 帮我写订单模块的 PRD
```

AI 会自动：
1. 读取 SKILL.md 中的流程定义
2. 检查项目内是否已有产物
3. 按模板生成产物，在头部写入 `upstream-document` 依赖表
4. 一站式执行完整性与一致性审计

## 项目结构

```
e2e-solution-guard/
├── SKILL.md                          # Skill 主文件（AI 的指令手册）
├── README.md                         # 本文件（给人类看的）
├── LICENSE                           # MIT
├── references/
│   ├── steps/                        # 各步骤模板
│   │   ├── prd-step.md               # PRD 模板
│   │   ├── interaction-step.md       # 交互设计模板
│   │   ├── ui-step.md                # UI 设计模板（产物：独立 HTML 文件）
│   │   ├── tech-step.md              # 技术方案模板
│   │   ├── test-step.md              # 测试报告模板
│   │   └── code-audit-report.md      # 代码审计报告模板
│   ├── top-level/                    # 顶层定义模板
│   │   ├── prd-top-level-template.md # PRD 顶层定义模板
│   │   ├── interaction-top-level-template.md # 交互顶层定义模板
│   │   ├── ui-top-level-template.md  # UI 顶层定义模板
│   │   └── tech-top-level-template.md # 技术顶层定义模板
│   ├── rules/                        # 一致性硬规则
│   │   └── consistency-rules.md      # 编号连续性、双向引用、术语一致性
│   └── workflow/                     # 执行流程
│       ├── idea-evaluation.md        # 想法评估流程
│       ├── document-workflow.md      # 产物生成/修改流程
│       ├── change-propagation.md     # 变更传播流程
│       ├── code-verification.md      # 代码验证流程
│       └── audit-procedure.md        # 审计执行策略
├── scripts/
│   └── doc-audit.py                  # 产物一致性审计脚本（标准库 only）
```

## 产物网络拓扑

从想法到代码的完整链路，按**产物线**拆分（C端、管理后台、车载、手表等）：

```
【项目级顶层定义】所有产物线共享
    │
    ├── 项目 PRD-顶层定义 ──┐
    ├── 项目交互-顶层定义 ──┼── 模块级产物引用 upstream
    ├── 项目 UI-顶层定义 ───┤
    └── 项目技术-顶层定义 ──┘
            │
            ▼
【模块级产物链】按产物线独立

C端产物线                管理后台产物线           车载端产物线
┌────────────┐          ┌────────────┐          ┌────────────┐
│ 用户管理    │          │ 用户管理    │          │ 用户管理    │
│ -PRD.md    │          │ -PRD.md    │          │ -PRD.md    │
│ (注册/登录) │          │ (表格/权限) │          │ (人脸登录) │
└─────┬──────┘          └─────┬──────┘          └─────┬──────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌────────────┐          ┌────────────┐          ┌────────────┐
│ 交互设计    │          │ 交互设计    │          │ 交互设计    │
│ -交互.md    │          │ -交互.md    │          │ -交互.md    │
│ (骨架)      │          │ (表格操作)  │          │ (语音控制)  │
└─────┬──────┘          └─────┬──────┘          └─────┬──────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌────────────┐          ┌────────────┐          ┌────────────┐
│ UI设计      │          │ UI设计      │          │ UI设计      │
│ -UI.html    │          │ -UI.html    │          │ -UI.html    │
│ (血肉拼合)  │          │ (密集表格)  │          │ (大按钮)    │
└─────┬──────┘          └─────┬──────┘          └─────┬──────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌────────────┐          ┌────────────┐          ┌────────────┐
│ 技术方案    │          │ 技术方案    │          │ 技术方案    │
│ -技术.md    │          │ -技术.md    │          │ -技术.md    │
│ (REST API)  │          │ (BFF/导出)  │          │ (CAN总线)   │
└─────┬──────┘          └─────┬──────┘          └─────┬──────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌────────────┐          ┌────────────┐          ┌────────────┐
│ 测试报告    │          │ 测试报告    │          │ 测试报告    │
│ -测试.md    │          │ -测试.md    │          │ -测试.md    │
│ (功能/异常) │          │ (数据/权限) │          │ (安全/法规) │
└─────┬──────┘          └─────┬──────┘          └─────┬──────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌────────────┐          ┌────────────┐          ┌────────────┐
│ 前端代码    │          │ 前端代码    │          │ 车载HMI    │
│ (React)     │          │ (Vue)       │          │ (Qt/Web)   │
└────────────┘          └────────────┘          └────────────┘
      │                       │                       │
      └───────────────────────┼───────────────────────┘
                              ▼ API调用
                    ┌──────────────────┐
                    │   后端代码仓库    │
                    │  ┌────────────┐  │
                    │  │ 用户服务    │  │
                    │  │ (Go/Java)  │  │
                    │  └────────────┘  │
                    └──────────────────┘
```

**关键设计**：
- 同一条业务线（如"用户管理"）在不同产物线中功能不同：C端是"注册/登录"，管理后台是"表格+权限"，车载是"人脸登录"
- 统一后端服务支撑所有产物线，不同产物线调用不同接口
- 模块级产物链（PRD→交互→UI→技术→测试）按产物线独立，变更互不影响

---

## 核心机制

### 1. 上游依赖声明

每份产物头部必须包含 `upstream-document` 表格：

```markdown
**上游文档**：

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| PRD-v1-订单模块 | 需求输入 | F001-F006 |
| 项目技术-顶层定义 | 规范继承 | 技术栈、公共表、接口约定 |
```

### 2. 变更时的双向约束

| 场景 | 规则 |
|------|------|
| **修改上游** | 分层扫描下游影响，用户确认后级联修改；拒绝则标注 `[待同步]` |
| **修改下游** | 逐条比对是否超出上游定义，超出则立即停止，先回改上游 |

### 3. 可运行的审计脚本

```bash
# 全量审计
python3 scripts/doc-audit.py PRD.md --type prd

# 增量审计（只检查变更的功能点）
python3 scripts/doc-audit.py PRD.md --type prd --delta F001,F003

# 扫描下游影响
python3 scripts/doc-audit.py PRD.md --type prd --scan-downstream ./docs/
```

审计覆盖：
- 编号连续性 & 重复检测
- upstream-document 引用有效性
- 表格格式完整性
- 接口一致性（技术方案产物：§4 接口设计 vs §13 接口清单）
- 术语一致性

### 4. 编号段分配

功能/页面编号按模块分段，解决并行开发冲突：

| 模块 | 功能编号段 | 页面编号段 |
|------|-----------|-----------|
| M01 订单模块 | F001-F099 | P001-P099 |
| M02 用户模块 | F100-F199 | P100-P199 |

模块内连续，段间允许跳号。

## 兼容性

- [Kimi Code CLI](https://github.com/MoonshotAI/kimi-cli)
- [Claude Code](https://github.com/anthropics/claude-code)
- [OpenAI Codex](https://github.com/openai/codex)

符合 [Agent Skills 开放格式](https://agentskills.io/)。

## License

[MIT](LICENSE)
