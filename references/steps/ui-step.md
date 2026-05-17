# UI 设计模板

> 定位：模块级视觉实现。
>
> **产物**：一个 HTML 文件（`{模块名}.html`），包含所有页面的原型。
>
> **边界**：只写视觉（颜色、尺寸、间距、阴影、圆角、字体），不写行为（触发条件、交互流程、状态机）。行为规则在交互设计中定义。

---

## 产物文件结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{模块名} UI 原型</title>
  <!--
    upstream:
    - 交互设计-v{版本}-{页面组名}.md（结构、行为）
    - 项目 UI-顶层定义.md（Token、组件库）
  -->
  <style>
    :root {
      /* CSS 变量，与项目 UI-顶层定义一致 */
      --primary: #1890ff;
      --primary-hover: #40a9ff;
      --text-primary: rgba(0, 0, 0, 0.88);
      --bg-page: #f0f2f5;
      /* ... */
    }
    /* 全局样式 */
    /* 状态样式: hover, active, focus, disabled, loading */
    /* 响应式: @media */
  </style>
</head>
<body>
  <!-- 页面1 -->
  <section id="page-001" class="page">
    <!-- 页面内容，静态假数据 -->
  </section>

  <!-- 页面2 -->
  <section id="page-002" class="page">
    <!-- 页面内容，静态假数据 -->
  </section>
</body>
</html>
```

---

## 约束

1. **一个文件**：一个模块只有一个 HTML 文件，所有页面用 `<section id="page-xxx">` 区分
2. **upstream 在注释中**：`<!-- upstream: 交互设计-xxx.md, UI-顶层定义.md -->`
3. **CSS 变量**：使用 `--*` 命名，与项目 UI-顶层定义一致
4. **状态样式**：必须包含 hover、active、focus、disabled、loading
5. **静态假数据**：不写 JS 业务逻辑、不写数据请求
6. **响应式**：`@media` 实现断点适配
7. **无行为逻辑**：不写 onclick、不写路由跳转、不写表单提交

---

## 与交互设计的关系

交互设计提供 SVG 线框图（结构）+ 状态矩阵（行为），UI 设计在此基础上添加视觉样式。

| 交互设计定义 | UI 设计实现 |
|-------------|------------|
| 页面结构（SVG 线框图） | HTML 结构 + CSS 布局 |
| 组件清单 | HTML 元素 + CSS 类 |
| 状态名称（默认/悬停/禁用） | CSS 伪类/类（:hover/.disabled） |
| 状态触发条件 | ❌ 不写（行为在交互设计中） |
| 状态交互行为 | ❌ 不写（行为在交互设计中） |

---

## 常见陷阱

- ❌ 拆分成多个 HTML 文件——一个模块一个文件
- ❌ 写 JS 业务逻辑——只写视觉
- ❌ 使用硬编码色值——必须用 CSS 变量
- ❌ 缺少 upstream 注释——头部必须声明上游
