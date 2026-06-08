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
  are propagated to downstream docs, or identify missing downstream updates,
  (6) transform or refactor existing artifacts to fully comply with skill standards
  (structure + content + semantic depth).
  For single-file audit, run `python3 "$HOME/.agents/skills/e2e-solution-guard/scripts/doc-audit.py"`.
---

# e2e-solution-guard

> 从想法到代码的全链路方案管理——用可追溯的依赖网络锁定事实，防止变更失控。

核心不是"写文档"，而是**管理从想法到代码的完整链路中的一切事实**。文档是事实的载体，价值在于：

- **任何想法落地前，先评估影响**：分析可行性、识别冲突、明确缺失信息
- **任何变更必须追溯上游、同步下游**：防止"改了需求忘了改代码"
- **任何实现必须与约定一致**：代码是事实的最终形态，文档是事实的约定形态

执行前读取项目 AGENTS.md。已有产物 → 按事实执行并检查上下游影响；没有 → 用本 skill 模板建立事实。

---

## 1. 核心原则

### 规范来源优先级

**项目已有产物 > Skill 模板**。产物未定义的部分，参照 Skill 模板。

### 行为约束

1. **对话式主动提问**：关键决策点（信息缺失/多义理解/影响多个下游/与已有产物矛盾）主动发起 1-3 个问题，提供选项让用户选。用户说"跳过"→记录最小假设继续。**禁止**一次性抛出长问卷。
2. **执行前做 gap 分析**：加载现有方案后，先识别缺失信息、潜在冲突和范围不明确处，再输出。禁止基于模糊想法直接输出。
3. **不要脑补，不要过度复杂化**：未定义的功能点、规则、字段、接口、状态值禁止自行补充。
4. **缺少前置定义禁止继续**：依赖的前置规范缺失时，暂停并询问用户是否补全。用户拒绝 → **立即停止**。
5. **逐步推进，一次只推进一个单元**：当前单元完成并确认无异常后，再开始下一个。禁止一次性批量输出多份产物。

### 产物关联

每份产物文件头部必须声明**上游文档**表格：引用了哪些上游文档、引用了上游的哪些内容（功能点编号/页面编号等）。

**变更约束**：

| 场景 | 操作 |
|------|------|
| 修改上游文档 | 扫描下游 → 列出影响范围 → 询问用户是否级联修改 → 用户确认则同步修改所有下游；用户拒绝则标注 `[待同步]` |
| 修改下游产物 | 读取所有上游 → 逐条比对是否在上游定义范围内 → 未超出则修改；超出则**立即停止**，先改上游 |

---

## 2. 何时加载哪个参考文件

| 场景 | 加载文件 | 说明 |
|------|---------|------|
| 生成/修改产物 | `references/workflow/document-workflow.md` | 前置检查、加载上下文、影响评估、生成/修改、审计 |
| 单文件审计 | `references/workflow/audit-procedure.md` + `references/steps/{类型}-step.md` + `references/checklists/{类型}-checklist.md` | 审计执行策略 + 产物结构参照 + 语义检查清单 |
| 批量审计 | `references/workflow/audit-batch.md` | 输出 `/goal` 命令序列 |
| 评估想法 | `references/workflow/idea-evaluation.md` | Gap 分析、方案融合、影响范围评估 |
| 发现上游缺陷需回改 | `references/workflow/change-propagation.md` | 下游扫描、级联修改、重新验证 |
| 代码已实现需验证 | `references/workflow/code-verification.md` + `references/workflow/code-audit-report.md` | 产物→代码闭环验证 + 审计报告模板 |
| 改造/重构现有产物 | `references/workflow/solution-transformation.md` | 结构+内容+语义全量重构 |
| 需要填写示例 | `references/examples/*-examples.md` | PRD/交互/UI/技术/测试的填写示例 |
| 跨产物链路检查 | `references/workflow/audit-checklists.md` | 全链路追溯检查清单索引 |

---

## 3. 脚本工具

```bash
python3 "$HOME/.agents/skills/e2e-solution-guard/scripts/doc-audit.py" <doc_path> --type <prd|interaction|ui|tech|test>
```

- 机械检查（格式、存在性、连续性、编号映射）
- 改造分析（`--migrate` / `--transform`）
- 改造分析（`--transform`）

---

*Skill 版本：v3.16*
