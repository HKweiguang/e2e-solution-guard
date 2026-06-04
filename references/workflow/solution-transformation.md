# 方案全量改造流程

> 当用户要求"改造"或"重构"现有产物时，按 skill 标准执行全量改造（结构 + 内容）。

---

## 触发条件

用户说以下任意一种表述时，触发本流程：

- "改造这份 PRD/方案/文档"
- "重构现有方案"
- "让这份文档符合模板要求"
- "按标准改造"

**禁止**：未经 `--transform` 分析直接按模板生成内容。

---

## 核心流程

```
[T1 全量诊断] → [T2 分批改造] → [T3 全量复验] → [T4 收尾]
```

---

### T1. 全量诊断

AI 自动执行：

```bash
SCRIPT="$HOME/.agents/skills/e2e-solution-guard/scripts/doc-audit.py"
[ -f "$SCRIPT" ] || SCRIPT=$(find ~/.agents/skills -name "doc-audit.py" -path "*/e2e-solution-guard/*" 2>/dev/null | head -1)
python3 "$SCRIPT" <产物路径> --type <type> --transform
```

提取关键信息：
- `missing_sections`：缺失章节
- `extra_sections`：多余章节
- `content_gaps`：已有章节的内容差距（空/占位符/缺表格/过短）
- `transformation_tasks`：完整改造任务列表（含 `task_id` / `target_section` / `priority`）
- `total_tasks`：任务总数

**决策分支**：
- 差距较小（任务数 ≤ 3，无 blocking）→ AI 自动执行改造，无需询问
- 差距较大（任务数 > 3 或有 blocking）→ 向用户简要汇报差异范围，确认后执行

---

### T2. 分批改造

#### 批次 1：结构调整（AI 主会话直接执行）

- 删除纯残留章节
- 调整章节顺序
- 新增章节插入占位符

#### 批次 2：内容深度改造（Agent 并行 —— **防偷懒核心**）

```
主会话（调度器）
├── 1. TodoList 初始化：所有任务写入 TodoList，状态 pending
├── 2. 读取：按任务清单准备上下文（模板 §4 要求 + 章节原文）
├── 3. Agent×N：前台并行启动子 agent（每任务一个，N ≤ 6）
│      启动前标记 in_progress
│      每个子 agent 输出：写入 transform-{task_id}.md
│      输出末尾必须包含：改造完成确认：{task_id}
├── 4. Bash 验证：文件存在、非空、含完成确认
│      通过 → 标记 done；失败 → 重跑
├── 5. 合并：主会话读取所有临时文件，合并为最终产物
└── 6. 覆盖率验证：TodoList 全 done 且 任务数 == total_tasks
```

**改造原则**：
- 保留已有事实，不脑补新功能点
- 按模板 §4 格式要求补充/重构
- 验证失败的任务必须重跑 Agent，禁止主会话自行补做

#### 批次 3：一致性修复（AI 主会话直接执行）

- 术语统一
- 编号连续性修复
- 双向引用修复

---

### T3. 全量复验

改造完成后自动执行，分阶段串行：

**阶段一：结构 + 链路复验（机械类检查）**

```bash
# 结构 + 内容复验（禁止沿用 T1 结果）
python3 "$SCRIPT" <产物路径> --type <type> --transform

# 链路检查（机械规则）
python3 "$SCRIPT" <产物路径> --type <type> \
  --upstream <上游> --top-level <顶层定义>
```

- `--transform` 和链路检查均无 blocking / warning → **通过**，进入阶段二
- 存在问题 → **停止**，修复后重新执行阶段一

**阶段二：语义检查（仅在阶段一通过后启动）**

```bash
python3 "$SCRIPT" --type <type> --model-checklist
```

**通过标准**：
- `missing_sections` 为空
- `content_gaps` 无 blocking 级问题
- `--model-checklist` 全部 `[模型]` 项通过（或存疑但已说明原因）

**硬性规则**：
- TodoList 非全 done → 禁止进入复验
- 复验发现新问题 → 新增任务到 TodoList，重新进入 T2
- 最多 3 轮（含初次）。第 3 轮仍不通过 → 向用户汇报

---

### T4. 收尾

- 更新产物头部版本标记
- 备份原文件为 `<原文件名>.backup.<日期>`
- 产出改造摘要

---

## 防偷懒机制

| 层级 | 机制 | 工具 |
|------|------|------|
| 任务清单 | 脚本穷举输出，AI 无权裁剪 | `--transform` |
| 进度跟踪 | TodoList 强制状态流转 | `TodoList` |
| 执行隔离 | 每任务一个子 Agent，独立文件输出 | `Agent` + `Write` |
| 输出验证 | Bash 脚本验证文件存在+格式 | `Bash` |
| 复验防漏 | 必须重新运行 `--transform`，禁止沿用旧结果 | `--transform` |

---

## 子 Agent Prompt 模板

````markdown
你是 e2e-solution-guard 的方案改造子 agent，任务 ID：{task_id}。

## 模板 §4 要求
{该章节在步骤模板中的 §4 格式要求}

## 产物当前内容
```
{产物中对应章节的原文}
```

## 改造指令
1. 保留已有事实，不脑补新功能点
2. 按模板 §4 要求补充/重构
3. 输出改造后的完整章节内容（Markdown 格式）
4. 输出改造说明
5. 最后必须输出：**改造完成确认：{task_id}**
````

---

## 约束

- 禁止删除用户原创内容
- 禁止跨步骤脑补
- 禁止主会话批量改写（必须通过子 Agent）
- 保留备份
