---
name: doc-chain
description: >
  Document chain management for software projects: generate, audit, and maintain PRDs,
  interaction designs, UI specs, technical designs, and test reports with upstream-downstream dependency tracking.
  Use when the user asks to: (1) create or modify any project documentation (PRD, tech design,
  interaction design, UI design, test plan, etc.), (2) check consistency between documents or
  between code and documents, (3) audit document structure, numbering continuity, cross-references,
  or error-code mappings, (4) ensure changes to upstream docs are propagated to downstream docs.
  Automatically loads document templates, runs doc-audit.py for mechanical checks, and enforces
  read-only subagent verification.
---

# doc-chain

> 用链式文档依赖网络约束 AI 行为——每份文档声明上游来源，变更必须全链路同步。修改上游必须同步下游，修改下游不得超出上游定义。文档是项目的唯一事实来源。

执行任何文档相关步骤前，先读取项目 AGENTS.md 了解项目信息，再检查项目内是否已有对应的文档。

- **有** → 按已有文档执行，同时检查上下游影响
- **没有** → 用本 skill 的模板生成文档

---

## 0. 参考流程（非强制）

以下是一种常见的步骤衔接方式，供项目参考：

```
[调研] → [PRD] → [交互设计] → [UI 设计] → [技术方案] → [测试]
          ↑                                          │
          └──── 发现上游问题需回改 ─────────────────────┘
```

步骤顺序由项目根据阶段决定，skill 不强制。每个步骤产出的文档数量（按模块、按端或其他方式拆分）由项目需求决定。

---

## 1. 何时加载哪个参考文件

| 场景 | 读取文件 | 说明 |
|------|---------|------|
| 生成或修改任何文档 | `references/workflow/document-workflow.md` | 阶段1-3完整流程：前置检查、加载上下文、影响评估、生成/修改、审计 |
| 发现上游缺陷需回改 | `references/workflow/change-propagation.md` | 回改触发、下游扫描、级联修改、重新验证 |
| 代码已实现，验证一致性 | `references/workflow/code-verification.md` | 文档→代码闭环：定位代码、五项对比、产出审计报告 |
| 启动审计 | `references/workflow/audit-procedure.md` | subagent审计方法、语义审计执行步骤、配置建议 |
| 需要具体步骤模板 | `references/steps/*-step.md` | PRD/交互/UI/技术/测试的文档结构和写作要求 |
| 需要顶层定义模板 | `references/top-level/*-top-level-template.md` | 全局规范模板（生成项目版本时参考） |
| 需要示例 | `references/examples/*-example.md` | 各步骤的示例文档 |
| 生成/修改后自查 | `references/rules/consistency-rules.md` | 编号连续性、双向引用、术语一致性、顶层定义交叉对齐等硬规则 |

---

## 2. 核心原则（常驻）

### 规范来源优先级

1. **项目已有文档** > **Skill 模板**。文档未定义的部分，参照 Skill 模板。

### 通用行为约束（适用于所有步骤）

- **执行前做 gap 分析，确认后再输出**：加载模板和上游后，先识别缺失信息，列成问题清单询问用户，禁止基于模糊需求直接输出
- **不要脑补，不要过度复杂化**：未定义的功能点、规则、字段、接口禁止自行补充
- **理性独立，不迎合，遇冲突/模糊必停**：发现不合理或与上下游矛盾的地方，必须明确提出质疑，禁止用默认假设继续
- **缺少前置定义禁止继续**：前置规范缺失时暂停，用户拒绝补全 → **立即停止**
- **逐步推进，一次只改一份文档**：当前文档完成并确认无异常后，再开始下一份

---

## 3. 模板清单

| 步骤 | 步骤模板 | 顶层定义模板 | 示例文档 |
|------|---------|-------------|---------|
| PRD | `references/steps/prd-step.md` | `references/top-level/prd-top-level-template.md` | `references/examples/prd-example.md` |
| 交互设计 | `references/steps/interaction-step.md` | `references/top-level/interaction-top-level-template.md` | `references/examples/interaction-example.md` |
| UI 设计 | `references/steps/ui-step.md` | `references/top-level/ui-top-level-template.md` | `references/examples/ui-example.md` |
| 技术方案 | `references/steps/tech-step.md` | `references/top-level/tech-top-level-template.md` | `references/examples/tech-example.md` |
| 测试 | `references/steps/test-step.md` | — | `references/examples/test-example.md` |
| 代码审计 | `references/steps/code-audit-report.md` | — | `references/examples/code-audit-example.md` |

**模板分工**：
- `top-level/` — 定义跨模块共享的规则体系。**注意**：这些文件是 Skill 内部模板，生成项目顶层定义时禁止将其中的元说明段落（「章节结构」「写作要求」「检查清单」等）复制到项目文档中
- `steps/` — 定义单个模块/步骤的文档结构和写作要求

---

## 4. 文档组织与关联

本 skill 的核心价值是帮助建立**可追溯的文档依赖网络**。各步骤按自己的最佳粒度自由拆分，文档之间通过文件头部的"上游文档"表格建立引用关系。目录结构由项目自定，唯一要求是**每份文档的文件头部必须声明上游输入**。

### 4.1 组织方式

- **按模块聚合**：同一模块的所有步骤文档放在一起
- **按步骤聚合**：同一职责的所有模块文档放在一起
- **按产品线或端拆分**：不同产品线或端的文档分开存放

以上可任意组合。

### 4.2 文档关联原则

每份文档必须通过文件头部的**上游文档**表格，声明：
1. **引用了哪些上游文档**（如 PRD、顶层定义、交互设计）
2. **引用了上游的哪些内容**（如功能点 `F001-F005`、页面 `P001-P003`）

**变更时的强制约束**：

| 场景 | 必须执行的操作 | 红线 |
|------|--------------|------|
| **修改上游文档** | 1. 分层扫描下游（`doc-audit.py --scan-downstream`）<br>2. 列出影响范围并按优先级排序<br>3. 询问用户是否级联修改<br>4. **用户确认** → 同步修改所有下游<br>5. **用户拒绝** → 标注 `[待同步]` | **禁止**不同步也不标注就留下不一致 |
| **修改下游文档** | 1. 读取所有上游文档<br>2. 逐条比对是否在上游定义范围内<br>3. **未超出** → 直接修改<br>4. **超出** → **立即停止**，先改上游 | **禁止**擅自扩展上游定义 |

**范围判定标准**：
- 功能点：功能编号对应关系不变
- 页面：页面范围在上游清单之内
- 状态/术语/错误码：值在上游顶层定义的枚举/规则之内

---

*Skill 版本：v1.5*
