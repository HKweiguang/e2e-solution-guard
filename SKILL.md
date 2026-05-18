---
name: e2e-solution-guard
description: >
  End-to-end solution management from idea to code: evaluate ideas, generate and maintain
  PRDs, interaction designs, UI prototypes, design systems, technical designs, and test reports
  with upstream-downstream dependency tracking. Enforces that any change traces back to
  upstream and syncs downstream, preventing implementation drift.
  Use when the user asks to: (1) evaluate, analyze, or refine a product idea, feature request,
  or technical proposal, (2) create, write, modify, or update any project documentation
  (PRD, requirements, tech design, interaction design, UI design, test plan, test cases, etc.),
  (3) review, audit, or check document quality, structure, completeness, numbering continuity,
  cross-references, or error-code mappings, (4) standardize, align, or check consistency
  between documents or between code and documents, (5) ensure changes to upstream docs
  are propagated to downstream docs, or identify missing downstream updates.
  Automatically loads document templates, runs `scripts/doc-audit.py` for mechanical checks, and enforces
  read-only subagent verification.
---

# e2e-solution-guard

> 从想法到代码的全链路方案管理——用可追溯的依赖网络锁定事实，防止变更失控。

e2e-solution-guard 的核心不是"写文档"，而是**管理从想法到代码的完整链路中的一切事实**。
文档只是事实的载体，真正的价值在于：

- **任何想法落地前，先评估影响**：分析可行性、识别与现有方案的冲突、明确缺失信息
- **任何变更必须追溯上游、同步下游**：防止"改了需求忘了改代码"
- **任何实现必须与约定一致**：代码是事实的最终形态，文档是事实的约定形态

执行任何步骤前，先读取项目 AGENTS.md 了解项目信息，再检查项目内是否已有对应的方案或产物。

- **有** → 按已有事实执行，同时检查上下游影响
- **没有** → 用本 skill 的模板建立事实

---

## 0. 参考流程（非强制）

以下是一种常见的步骤衔接方式，供项目参考：

```
[调研] → [PRD] → [交互设计] → [UI 设计] → [技术方案] → [测试]
          ↑                                       │
          └──── 发现上游问题需回改 ─────────────────┘
```

**模块级视觉实现**：交互设计提供 SVG 线框图（结构）+ 状态矩阵（行为），UI 设计产出 HTML 原型（视觉实现）。

步骤顺序由项目根据阶段决定，skill 不强制。每个步骤产出的产物数量（按模块、按端或其他方式拆分）由项目需求决定。

---

## 1. 何时加载哪个参考文件

| 场景 | 读取文件 | 说明 |
|------|---------|------|
| 评估想法、需求或技术方案 | `references/workflow/idea-evaluation.md` | Gap分析、方案融合判断、影响范围评估、可行性结论 |
| 生成或修改任何产物 | `references/workflow/document-workflow.md` | 阶段1-3完整流程：前置检查、加载上下文、影响评估、生成/修改、审计 |
| 发现上游缺陷需回改 | `references/workflow/change-propagation.md` | 回改触发、下游扫描、级联修改、重新验证 |
| 代码已实现，验证一致性 | `references/workflow/code-verification.md` | 产物→代码闭环：定位代码、五项对比、产出审计报告 |
| 启动审计 | `references/workflow/audit-procedure.md` | subagent审计方法、语义审计执行步骤、配置建议 |
| 需要具体步骤模板 | `references/steps/*-step.md` | PRD/交互/UI/技术/测试的产物结构和写作要求 |
| 需要顶层定义模板 | `references/top-level/*-top-level-template.md` | 全局规范模板（生成项目版本时参考） |
| 生成/修改后自查 | `references/rules/consistency-rules.md` | 编号连续性、双向引用、术语一致性、顶层定义交叉对齐等硬规则 |

---

## 2. 核心原则（常驻）

### 规范来源优先级

1. **项目已有产物** > **Skill 模板**。产物未定义的部分，参照 Skill 模板。

### 通用行为约束（适用于所有方案分析与设计工作）

- **执行前做 gap 分析，确认后再输出**：加载现有方案和上下文后，先识别缺失信息、潜在冲突和范围不明确的地方，列成问题清单询问用户。禁止基于模糊想法直接输出完整方案、产物或代码
- **不要脑补，不要过度复杂化**：未定义的功能点、规则、字段、接口、状态值禁止自行补充。避免在用户要求之外增加不必要的复杂度、层级或依赖
- **理性独立，不迎合，遇冲突/模糊必停**：基于专业判断分析用户需求，发现不合理、有风险、与最佳实践冲突或与现有方案矛盾的地方，必须明确提出质疑和建议。遇到需求不明确、规范冲突、技术不可行等情况，禁止用默认假设继续
- **缺少前置定义禁止继续**：当前工作依赖的前置规范（产物/接口/配置/顶层定义）缺失时，暂停并询问用户是否补全。用户拒绝 → **立即停止**
- **逐步推进，一次只推进一个单元**：当前分析、产物或代码单元完成并确认无异常后，再开始下一个。禁止一次性批量输出多份产物或大范围改动

---

## 3. 模板清单

| 步骤 | 步骤模板 | 顶层定义模板 |
|------|---------|-------------|
| PRD | `references/steps/prd-step.md` | `references/top-level/prd-top-level-template.md` |
| 交互设计 | `references/steps/interaction-step.md` | `references/top-level/interaction-top-level-template.md` |
| UI 设计 | `references/steps/ui-step.md` | `references/top-level/ui-top-level-template.md` |
| 技术方案 | `references/steps/tech-step.md` | `references/top-level/tech-top-level-template.md` |
| 测试 | `references/steps/test-step.md` | — |
| 代码审计 | `references/steps/code-audit-report.md` | — |

**模板分工**：
- `top-level/` — 定义跨模块共享的规则体系。**注意**：这些文件是 Skill 内部模板，生成项目顶层定义时禁止将其中的元说明段落（「章节结构」「写作要求」「检查清单」等）复制到项目产物中
- `steps/` — 定义单个模块/步骤的产物结构和写作要求

---

## 4. 产物组织与关联

本 skill 的核心价值是帮助建立**可追溯的产物依赖网络**。各步骤按自己的最佳粒度自由拆分，产物之间通过文件头部的"上游文档"表格建立引用关系。目录结构由项目自定，唯一要求是**每份产物的文件头部必须声明上游输入**。

### 4.1 组织方式

- **按模块聚合**：同一模块的所有步骤产物放在一起
- **按步骤聚合**：同一职责的所有模块产物放在一起
- **按产品线或端拆分**：不同产品线或端的产物分开存放

以上可任意组合。

### 4.2 产物关联原则

每份产物必须通过文件头部的**上游文档**表格，声明：
1. **引用了哪些上游产物**（如 PRD、顶层定义、交互设计）
2. **引用了上游的哪些内容**（如功能点 `USER-001`–`USER-005`、页面 `PAGE-001`–`PAGE-003`）

**变更时的强制约束**：

| 场景 | 必须执行的操作 | 红线 |
|------|--------------|------|
| **修改上游产物** | 1. 分层扫描下游（`scripts/doc-audit.py --scan-downstream`）<br>2. 列出影响范围并按优先级排序<br>3. 询问用户是否级联修改<br>4. **用户确认** → 同步修改所有下游<br>5. **用户拒绝** → 标注 `[待同步]` | **禁止**不同步也不标注就留下不一致 |
| **修改下游产物** | 1. 读取所有上游产物<br>2. 逐条比对是否在上游定义范围内<br>3. **未超出** → 直接修改<br>4. **超出** → **立即停止**，先改上游 | **禁止**擅自扩展上游定义 |

**范围判定标准**：
- 功能点：功能编号对应关系不变
- 页面：页面范围在上游清单之内
- 状态/术语/错误码：值在上游顶层定义的枚举/规则之内

---

*Skill 版本：v2.8*
