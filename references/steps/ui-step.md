# UI 设计模板（可选）

> 定位：**可选步骤**。当项目使用成熟组件库且交互设计已覆盖状态矩阵时，开发人员可直接根据交互文档和组件库实现，无需单独的 UI 设计文档。
>
> 仅在以下情况生成本文档：
> 1. 模块包含**自定义视觉**（品牌色、非标准组件、特殊动效）
> 2. 需要定义**响应式适配规则**（断点、布局变化）
> 3. 包含**模块特有组件**（组件库中不存在，需完整样式定义）
>
> AI 生成的是**HTML 高保真原型**（可直接在浏览器中预览的独立 HTML 代码块），不是文字规范，也不是图像。每个页面的 HTML 代码块可以单独保存为 `.html` 文件并在浏览器中打开。

---

## §1 文档信息

```markdown
# UI设计-v{主版本号}-{页面组名/模块名}

**覆盖功能点**：{功能编号}, {功能编号}, ...
**覆盖页面**：{页面编号}, {页面编号}, ...
**版本号**：v{主版本号}.{补丁号}
**制定日期**：YYYY-MM-DD
**作者**：姓名

**上游文档**：
> 以下仅为该步骤常见依赖的示例，实际生成时需根据项目上下文动态判断，不要机械套用。

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| 交互设计-{页面组名} | 设计输入 | {页面编号范围}, 信息架构、组件交互、状态机、页面流程 |
| 项目 UI-顶层定义 | 规范继承 | 设计原则（§1）、设计令牌体系（§2）、色彩系统（§3）、字体系统（§4）、间距与布局系统（§5）、形状系统（§6）、阴影与海拔（§7）、图标规范（§9）、主题与暗黑模式（§10）、组件库（§11） |
```

---

## §2 章节结构

UI 设计文档以**页面**为主线组织。每个页面为一个一级章节。

**文档级章节**（整个文档只出现一次）：

| 章节 | 说明 |
|------|------|
| 设计系统引用 | 声明继承的顶层视觉规范，以 CSS 变量形式呈现 Token 映射 |

**页面级章节**（每个页面重复，标题格式：`## §N {页面编号} {页面名}`）：

| 子节 | 说明 |
|------|------|
| HTML 原型 | 可在浏览器中预览的独立 HTML 代码块，包含内联 CSS 和静态假数据 |
| 与交互设计对应 | 交互页面编号、组件清单、状态映射、跳转目标 |

---

## §3 UI不写的

| 不写 | 原因 | 应该在哪 |
|------|------|---------|
| 交互设计（状态机、页面流转、手势规则） | 行为规则不属于视觉实现 | `interaction-step.md` |
| 技术实现（架构、接口、数据模型） | 实现方案不属于视觉实现 | `tech-step.md` |
| 测试策略（测试用例、测试范围） | 验证方法不属于视觉实现 | `test-step.md` |
| 业务逻辑（数据请求、条件判断、事件处理） | UI 原型只展示视觉，不执行业务 | `tech-step.md` |

**越界检测**：若 UI 设计中出现类似"点击 XX 按钮后调用 XX 接口"的技术描述，或"当 XX 条件满足时显示"的业务逻辑描述，应标记为**越界内容**，提示用户移至对应步骤。

---

## §4 各章节格式要求

### 4.1 设计系统引用（文档级）

**内容**：声明本模块 UI 稿继承的顶层视觉规范，以 **CSS 变量代码块** 的形式呈现 Token 映射。此代码块作为"规范层"，定义本模块所有页面共享的 CSS 变量。

**格式建议**：`css` 代码块。变量命名与项目 UI-顶层定义 §2 的 Token 命名规范一致。

> 此章节在文档中只出现一次，位于文件头部之后、第一个页面章节之前。

**填写示例**：

```css
:root {
  /* 色彩 Token */
  --primary: #1890ff;
  --primary-hover: #40a9ff;
  --primary-active: #096dd9;
  --on-primary: #ffffff;
  --text-primary: rgba(0, 0, 0, 0.88);
  --text-secondary: rgba(0, 0, 0, 0.45);
  --text-disabled: rgba(0, 0, 0, 0.25);
  --bg-page: #f0f2f5;
  --surface: #ffffff;
  --border-default: #d9d9d9;
  --error: #ff4d4f;
  --success: #52c41a;

  /* 字体 Token */
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-size-h1: 24px;
  --font-size-h2: 20px;
  --font-size-body: 14px;
  --font-size-caption: 12px;
  --font-weight-medium: 500;
  --font-weight-bold: 600;
  --line-height-body: 1.5;

  /* 间距 Token */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* 圆角 Token */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --radius-full: 999px;

  /* 阴影 Token */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.1);
}
```

**常见陷阱**：
- ❌ 只写"继承项目 UI-顶层定义"，不输出具体的 CSS 变量代码块
- ❌ 变量命名与项目 UI-顶层定义 §2 不一致——导致开发映射困难
- ❌ 在 HTML 原型中直接使用硬编码色值（如 `#1890ff`）而不通过 CSS 变量

---

### 4.2 HTML 原型（页面级）

**内容**：每个页面对应一个**独立的完整 HTML 文档**代码块，可在浏览器中直接预览。

**格式要求**：

1. **独立完整**：包含 `<!DOCTYPE html>`、`<html>`、`<head>`、`<body>`，可单独保存为 `.html` 文件运行
2. **内联样式**：所有 CSS 写在 `<style>` 标签中，不依赖外部文件
3. **CSS 变量**：使用 `--*` 命名的 CSS 变量，命名与 §2 设计系统引用一致
4. **状态覆盖**：通过 CSS 伪类和状态类实现交互状态（`:hover`、`:active`、`:focus`、`.disabled`、`.loading`）
5. **静态假数据**：使用写死的示例数据，不写 JS 数据请求逻辑
6. **响应式**：通过 `@media` 实现断点适配（如需要）

**边界**：
- 不写 JS 业务逻辑（数据获取、条件判断、路由跳转）
- 不写表单提交逻辑
- 链接和按钮的 `href`/`onclick` 留空或使用 `javascript:void(0)`

**填写示例**（工单列表页）：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>工单列表</title>
  <style>
    :root {
      /* 引用 §2 定义的 CSS 变量（本页面需要的最小子集） */
      --primary: #1890ff;
      --primary-hover: #40a9ff;
      --primary-active: #096dd9;
      --on-primary: #ffffff;
      --text-primary: rgba(0, 0, 0, 0.88);
      --text-secondary: rgba(0, 0, 0, 0.45);
      --text-disabled: rgba(0, 0, 0, 0.25);
      --bg-page: #f0f2f5;
      --surface: #ffffff;
      --border-default: #d9d9d9;
      --space-md: 16px;
      --space-lg: 24px;
      --radius-sm: 4px;
      --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
      --font-size-body: 14px;
      --font-size-caption: 12px;
      --font-weight-medium: 500;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: var(--font-size-body);
      background: var(--bg-page);
      color: var(--text-primary);
    }
    /* 按钮状态 */
    .btn {
      display: inline-flex;
      align-items: center;
      padding: 6px 16px;
      border: none;
      border-radius: var(--radius-sm);
      background: var(--primary);
      color: var(--on-primary);
      font-size: var(--font-size-body);
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover { background: var(--primary-hover); }
    .btn:active { background: var(--primary-active); }
    .btn:focus {
      outline: 2px solid var(--primary);
      outline-offset: 2px;
    }
    .btn.disabled, .btn:disabled {
      background: var(--text-disabled);
      cursor: not-allowed;
      opacity: 0.6;
    }
    .btn.loading::after {
      content: " ⌛";
    }
    /* 表格 */
    .table {
      width: 100%;
      background: var(--surface);
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-sm);
    }
    .table th, .table td {
      padding: var(--space-md);
      border-bottom: 1px solid var(--border-default);
      text-align: left;
    }
    .table th {
      font-weight: var(--font-weight-medium);
      color: var(--text-secondary);
      font-size: var(--font-size-caption);
    }
    .table tbody tr:hover { background: rgba(0, 0, 0, 0.02); }
    /* 标签 */
    .tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: var(--radius-sm);
      font-size: var(--font-size-caption);
    }
    .tag-primary { background: #e6f7ff; color: #096dd9; }
    /* 布局 */
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: var(--space-lg);
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: var(--space-lg);
    }
    /* 响应式 */
    @media (max-width: 768px) {
      .container { padding: var(--space-md); }
      .header { flex-direction: column; gap: var(--space-md); align-items: flex-start; }
      .table th, .table td { padding: var(--space-sm); }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>工单管理</h1>
      <button class="btn">新建工单</button>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>工单编号</th>
          <th>客户姓名</th>
          <th>状态</th>
          <th>创建时间</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>T-2024-001</td>
          <td>张三</td>
          <td><span class="tag tag-primary">待处理</span></td>
          <td>2024-01-15 10:30</td>
        </tr>
        <tr>
          <td>T-2024-002</td>
          <td>李四</td>
          <td><span class="tag tag-primary">处理中</span></td>
          <td>2024-01-15 11:00</td>
        </tr>
      </tbody>
    </table>
  </div>
</body>
</html>
```

**常见陷阱**：
- ❌ HTML 代码块不是完整文档（缺少 `<html>`/`<head>`/`<body>`）——无法直接保存预览
- ❌ 使用外部 CSS 文件引用——需要额外文件，不便独立预览
- ❌ 缺少状态样式（只有默认态，无 hover/active/focus/disabled）——开发无法还原交互状态
- ❌ 写 JS 业务逻辑——越界到技术实现
- ❌ 使用真实数据或动态渲染——应该是静态假数据
- ❌ CSS 中直接写硬编码色值而非 `var(--*)`——破坏 Token 一致性

---

### 4.3 与交互设计对应（页面级）

**内容**：标注本模块所有 UI 页面对应的交互设计页面编号、组件清单、状态映射。页面内涉及的所有跳转/链接目标，需标注目标页面编号或外部文档引用。

**格式建议**：表格。列：**UI 页面 | 交互页面编号 | 涉及组件 | 状态映射 | 跳转目标**。

> **状态映射说明**：交互设计定义了"有哪些状态"，UI 设计的 HTML 原型通过 CSS 实现了这些状态的视觉表现。本列简要标注每个组件在 HTML 中实现了哪些状态（如"Button: hover/active/focus/disabled/loading"）。

**填写示例**：

| UI 页面 | 交互页面编号 | 涉及组件 | 状态映射 | 跳转目标 |
|---------|-------------|---------|---------|---------|
| 工单列表页 | PAGE-TICKET-001 | Table、Button、Tag | Button: hover/active/focus/disabled<br>Table: hover<br>Tag: 无 | PAGE-TICKET-002（详情）、PAGE-TICKET-003（创建）|
| 工单详情页 | PAGE-TICKET-002 | Card、Button、Timeline | Button: hover/active/focus/disabled/loading | PAGE-TICKET-001（返回列表）|

**常见陷阱**：
- ❌ UI 页面与交互页面编号不一致——导致需求追溯困难
- ❌ 遗漏交互设计中定义的组件——导致功能遗漏
- ❌ 状态映射与交互设计的状态机不一致——如交互定义了加载态但 HTML 未实现

---

## §5 格式规范

### 5.1 CSS 变量命名

- 必须与项目 UI-顶层定义 §2 的 Token 命名规范一致
- 颜色变量：`--{用途}`、`--{用途}-{状态}`（如 `--primary`、 `--primary-hover`）
- 字体变量：`--font-{属性}-{层级}`（如 `--font-size-body`）
- 间距变量：`--space-{规模}`（如 `--space-md`）
- 圆角变量：`--radius-{规模}`（如 `--radius-sm`）
- 阴影变量：`--shadow-{层级}`（如 `--shadow-md`）
- 禁止在 HTML 原型的 CSS 中直接使用 HEX/RGB 值，必须通过 CSS 变量引用

**常见陷阱**：
- ❌ 使用项目 UI-顶层定义中未声明的变量名——开发找不到对应 Token
- ❌ 同一变量在不同页面写不同值——如 `--primary` 在 A 页面是 `#1890ff`，B 页面是 `#1677ff`
- ❌ 硬编码色值与 CSS 变量混用——维护时无法通过修改变量统一调整

### 5.2 状态类命名

- 悬停态：CSS 伪类 `:hover`
- 按下态：CSS 伪类 `:active`
- 聚焦态：CSS 伪类 `:focus` 或 `:focus-visible`
- 禁用态：`.disabled` 类 或 `:disabled` 伪类
- 加载态：`.loading` 类
- 空状态、错误状态、成功状态、骨架态：在页面容器上使用 `.empty`、`.error`、`.success`、`.skeleton` 类

### 5.3 响应式断点

- 断点值与项目 UI-顶层定义 §5 一致
- 通过 `@media` 在 HTML 的 `<style>` 中实现
- 每个断点需说明布局变化和组件调整

### 5.4 假数据规则

- 使用写死的示例数据，明确标注为"示例"
- 数据格式与 PRD 数据模型一致（字段名、数据类型）
- 至少包含 2 条示例数据，展示列表/表格的常规状态
- 如需展示空状态，单独写一个 HTML 代码块或在注释中说明

### 5.5 文案规范

- 必须与交互设计逐字一致
- 禁止自行修改文案
- 发现不一致 → 停止生成，询问用户以哪个为准

---

## §6 检查清单

### 6.1 一致性检验

- [ ] **结构一致性** `[脚本]`：每个页面包含 2 个子节（HTML 原型、与交互设计对应），且文档包含 1 个文档级章节（设计系统引用）
- [ ] **范围一致性** `[模型]`：所有页面编号在上游交互设计页面清单内；所有组件在上游交互设计的组件清单内
- [ ] **Token 一致性** `[脚本]`：HTML 原型中的 CSS 变量命名与项目 UI-顶层定义 §2 一致；无硬编码色值（必须通过 `var(--*)` 引用）
- [ ] **状态映射一致性** `[模型]`：HTML 原型中实现的 CSS 状态（hover/active/focus/disabled/loading）与交互设计的组件交互子节中定义的状态一致
- [ ] **内部自洽性** `[模型]`：本文档涉及的所有页面编号在「与交互设计对应」子节中都有标注；同一页面内 CSS 变量引用与设计系统引用声明一致
- [ ] **跨文档链路一致性** `[模型]`（如已有下游文档）：每个 HTML 原型中的组件样式在下游技术方案前端实现中有对应 CSS；每个 CSS 变量在下游代码仓库中有对应变量定义

### 6.2 完整性检验

- [ ] 设计系统引用（文档级章节）已声明继承的顶层规范，并以 CSS 变量代码块呈现 `[脚本]`
- [ ] 每个页面的 HTML 原型子节包含一个完整的 HTML 代码块（含 `<!DOCTYPE html>`、 `<html>`、 `<head>`、 `<body>`） `[脚本]`
- [ ] 每个 HTML 原型使用 CSS 变量（`var(--*)`）引用 Token `[脚本]`
- [ ] 每个 HTML 原型包含至少 4 种交互状态样式（hover/active/focus/disabled 或 loading） `[脚本]`
- [ ] 每个 HTML 原型使用静态假数据（无 JS 业务逻辑、无数据请求） `[脚本]`
- [ ] 每个页面的「与交互设计对应」子节包含交互页面编号、组件清单、状态映射 `[脚本]`
- [ ] 所有跳转目标页面要么在本文档范围内，要么正确引用外部文档 `[脚本]`
- [ ] §5 格式规范已遵循（CSS 变量命名、状态类命名、响应式断点、假数据规则、文案一致） `[脚本]`
