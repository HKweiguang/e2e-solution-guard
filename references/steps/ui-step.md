# UI 设计模板

> 定位：模块级视觉实现。
>
> **核心思想**：交互设计是骨架，UI 顶层定义是血肉。UI 设计稿就是把这两者拼起来，展示最终长什么样。
>
> **边界**：只写视觉（颜色、尺寸、间距、阴影、圆角、字体），不写行为（触发条件、交互流程、状态机）。

**上游文档**：

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| 交互设计-{页面组}（单角色）或 交互设计-{角色}-{页面组}（多角色） | 结构输入 | SVG 线框图 → HTML 结构；状态矩阵 → 状态类/伪类名称映射（行为状态定义，不含视觉值） |
> 注：单角色项目只有一个交互设计文件；多角色项目交互设计按角色分文件。UI 按角色+设备分文件，一个 HTML 只展示一种设备的界面。
| 项目 UI-顶层定义 | 规范继承 | Token → CSS 变量；组件库 → HTML 元素；平台视觉规范（§2.12，多端项目适用）→ 平台状态差异、组件尺寸、安全区 |

---

## §1 设计系统引用

```css
:root {
  /* 来自项目 UI-顶层定义的 CSS 变量 */
}
```

---

## §2 HTML 原型

产物文件：`ui-{设备}-{页面组}.html`（单角色）或 `ui-{角色}-{设备}-{页面组}.html`（多角色）
> 示例：`ui-web-首页.html`（单角色）、`ui-{角色}-web-首页.html`（多角色）

```html
<!DOCTYPE html>
<html>
<head>
  <!-- upstream: 交互设计-{页面组}.md, 项目 UI-顶层定义.md -->
  <style>
    :root {
      /* CSS 变量来自项目 UI-顶层定义，如 --primary、--text-primary 等 */
    }
    .btn { background: var(--primary); }
    .btn:hover { opacity: 0.8; }
    /* 状态样式: hover / active / focus / disabled / loading */
    /* 响应式: @media */
  </style>
</head>
<body>
  <!--
  状态映射表（关节层）：
  | 交互状态 | CSS 类/伪类 | Token 变量 | 技术方案引用 |
  | 默认态   | （无）       | —          | Button 组件 default 样式 |
  | 悬停态   | :hover       | --primary-hover | Button 组件 hover 样式 |
  | 按下态   | :active      | --primary-active | Button 组件 active 样式 |
  | 禁用态   | .disabled    | --disabled | Button 组件 disabled 属性 |
  | 加载态   | .loading     | --primary + opacity: 0.7 | Button 组件 loading 状态 |
  -->
  <section id="page-001"> <!-- 静态假数据，无 JS --> </section>
  <section id="page-002"> <!-- 静态假数据，无 JS --> </section>
</body>
</html>
```

原则：
- 一个页面组一个文件
- CSS 变量全部来自项目 UI-顶层定义
- 状态用伪类实现
- 静态原型，无 JS 业务逻辑

---

## §3 与交互设计对应

### 3.1 页面映射

| UI 页面 | 交互页面编号 | 对应 `<section id>` |
|---------|-------------|-------------------|
| 页面1 | PAGE-PROFILE-001 | page-profile-001 |
| 页面2 | PAGE-ORDER-001 | page-order-001 |

### 3.2 状态映射表（关节层）

> **核心作用**：显式声明"交互设计定义的状态名称 → UI 实现的 CSS 类/伪类 → UI-顶层定义 Token → 技术方案引用"的完整映射链。禁止让映射关系隐式散落在 HTML 代码中。

**格式**：每个页面一张状态映射表。列：**交互状态 | CSS 类/伪类 | Token 变量 | 技术方案引用**。

**填写示例**（PAGE-PROFILE-001 个人资料页）：

| 交互状态 | CSS 类/伪类 | Token 变量 | 技术方案引用 |
|---------|------------|-----------|-------------|
| 默认态 | （无） | — | Button 组件 default 样式 |
| 悬停态 | `:hover` | `--color-primary-hover` | Button 组件 hover 样式 |
| 按下态 | `:active` | `--color-primary-active` | Button 组件 active 样式 |
| 聚焦态 | `:focus-visible` | `--focus-ring` | Button 组件 focus 样式 |
| 禁用态 | `.disabled` / `:disabled` | `--color-disabled` | Button 组件 disabled 属性 |
| 加载态 | `.loading` | `--color-primary` + `opacity: 0.7` | Button 组件 loading 状态 |
| 空状态 | `.empty` | `--color-text-secondary` | Empty 组件 |
| 错误状态 | `.error` | `--color-error` | Form 组件 error 样式 |
| 成功状态 | `.success` | `--color-success` | Toast 组件 success 样式 |
| 骨架态 | `.skeleton` | `--color-skeleton` | Skeleton 组件 |

**常见陷阱**：
- ❌ 映射表只列状态名，不写 CSS 类名——开发人员无法确定用 `:hover` 还是 `.hover`
- ❌ 映射表不写 Token 变量——无法追溯视觉规范来源
- ❌ 映射表不写技术方案引用——下游技术方案无法对齐组件选型
- ❌ 交互设计更新了状态名（如"按下态"改为"激活态"），映射表未同步更新

> 基础状态：default（默认态）、hover（悬停态）、active（按下态）、focus（聚焦态）、disabled（禁用态）、loading（加载态）
> 异步状态：empty（空状态）、error（错误状态）、success（成功状态）、skeleton（骨架态）

---

## §4 UI 设计不写的

| 不写 | 原因 | 应该在哪 |
|------|------|---------|
| 交互行为（触发条件、状态流转、页面跳转） | 行为规则不属于视觉规范 | `interaction-step.md` |
| 产品需求（功能点、业务规则、验收标准） | 需求定义不属于视觉实现 | `prd-step.md` |
| 技术实现（架构、接口、数据模型） | 实现方案不属于视觉设计 | `tech-step.md` |
| 测试策略（测试用例、测试范围） | 验证方法不属于视觉设计 | `test-step.md` |

**越界检测**：若 UI 设计中出现类似"点击后跳转到XX页面"的交互描述，或"调用XX接口"的技术描述，或"功能点F001的验收标准是..."的需求描述，应标记为**越界内容**，提示用户移至对应步骤。

---

## §5 检查清单

### 结构一致性 `[脚本]`
- [ ] §1 设计系统引用了项目 UI-顶层定义的 CSS 变量
- [ ] §2 HTML 原型包含完整的 `<!DOCTYPE html>` 文档结构
- [ ] §2 HTML 原型在 `<head>` 或 `<style>` 中声明了 upstream 注释
- [ ] §3 与交互设计对应表格覆盖了本页面组的所有页面
- [ ] §3.2 状态映射表覆盖了交互设计定义的全部基础状态和异步状态
- [ ] §3.2 状态映射表每行包含：交互状态、CSS 类/伪类、Token 变量、技术方案引用
- [ ] §3.2 状态映射表中的 CSS 类名与 §2 HTML 原型中的实际类名一致

### 范围一致性 `[脚本]`
- [ ] 每个 `<section id="page-xxx">` 对应交互设计中的一个页面编号
- [ ] CSS 变量命名与项目 UI-顶层定义的 Token 命名一致
- [ ] 无硬编码色值（全部使用 `var(--*)` 引用 CSS 变量）

### 格式一致性 `[脚本]`
- [ ] HTML 代码块语法正确，可在浏览器中直接打开预览
- [ ] 表格格式完整，无空列或错位

### 语义一致性 `[模型]`
- [ ] 各状态之间的视觉差异足够明显，用户可区分
- [ ] 禁用态有明确的视觉区分（不仅颜色变化，还需考虑色盲用户）
- [ ] 加载态保留了上下文（非全白屏）
- [ ] 响应式断点与项目 UI-顶层定义 §2.5.5 一致
- [ ] 多端项目时，平台状态差异（Web hover / App pressed）与项目 UI-顶层定义 §2.12 一致
- [ ] 每个组件状态类名在下游技术方案中有对应引用（前端组件库选型、样式实现方案）
- [ ] **边界一致性** `[模型]`：产物中无不属于 UI 范畴的行为描述（触发条件、交互流程、页面跳转、状态流转、校验规则）
