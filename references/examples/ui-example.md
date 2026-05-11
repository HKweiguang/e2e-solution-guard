# UI设计-订单交易页面

**覆盖功能点**：F001, F002, F003, F004, F005, F006
**覆盖页面**：P001, P002, P003, P004, P005, P006
**版本号**：v1.0.0
**制定日期**：2024-01-15
**作者**：示例团队

**上游文档**：

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| 交互设计-订单交易流程 | 设计输入 | F001-F006, P001-P006 |
| 项目 UI 全局规范 | 规范继承 | 色彩、字体、组件系统 |

---

## §1 全局规范引用

本页面 UI 稿继承项目 UI 全局规范的色彩系统、字体系统和组件系统。全局 Token 直接引用，不重复定义。

色彩使用：`primary-500`、`text-primary`、`text-secondary`、`bg-surface`、`border-light` 等。
间距使用：`spacing-md`、`spacing-lg`、`radius-md` 等。

---

## §2 页面组件

### 2.1 订单状态标签

**用途**：在订单列表和订单详情中展示订单当前状态。
**结构**：圆角矩形标签，内含状态文案。
**样式**：
- 宽度：自适应文案 + `spacing-md` 左右内边距
- 高度：24px
- 圆角：`radius-full`
- 字体：`text-xs`，`font-medium`
- 各状态配色：
  - PENDING：`warning-100` 背景，`warning-600` 文字
  - PAID：`success-100` 背景，`success-600` 文字
  - SHIPPED：`primary-100` 背景，`primary-600` 文字
  - COMPLETED：`neutral-100` 背景，`neutral-600` 文字
  - CANCELLED：`neutral-100` 背景，`neutral-400` 文字

---

## §3 组件规范

### 3.1 全局组件引用清单

| 组件名称 | 引用 Token | 说明 |
|---------|-----------|------|
| Button-Primary | `primary-500` / `text-inverse` | 用于主操作：立即购买、提交订单、去结算 |
| Button-Secondary | `surface-elevated` / `text-primary` | 用于次要操作：加入购物车、取消订单 |
| Button-Text | `text-primary` | 用于文字按钮：管理、查看物流 |
| Input | `border-light` / `radius-md` | 搜索输入框、数量输入 |
| Card | `bg-surface` / `radius-lg` / `shadow-sm` | 商品卡片、订单卡片、地址卡片 |
| ListItem | `bg-surface` / `border-bottom` | 商品项、订单项 |
| Badge | 参见 §2.1 订单状态标签 | 模块特有变体 |

### 3.2 模块特有组件

| 组件名称 | 宽度 | 高度 | 圆角 | 背景色 | 文字色 | 说明 |
|---------|------|------|------|--------|--------|------|
| 步进器 | 100px | 32px | `radius-sm` | `bg-surface` | `text-primary` | 购物车数量调整：- 按钮 / 数字 / + 按钮 |
| 地址卡片 | 100% - 2×`spacing-lg` | 自适应 | `radius-lg` | `bg-surface` | `text-primary` | 订单确认页地址展示，带右箭头 |
| 金额行 | 100% | 44px | — | — | `text-primary`/`text-secondary` | 左对齐标签，右对齐金额，实付金额用 `text-lg` `font-bold` |

---

## §4 页面设计

### 4.1 P001 商品列表

**默认状态**：
- 顶部搜索栏：高度 48px，`bg-surface`，搜索框圆角 `radius-full`，左侧搜索图标 `neutral-400`
- 分类筛选栏：高度 44px，横向滚动，选中项底部 2px `primary-500` 下划线，文字 `primary-500` `font-medium`
- 商品卡片：两列网格，间距 `spacing-md`，卡片内边距 `spacing-sm`
  - 封面图：宽高比 3:4，`radius-md`
  - 书名：`text-sm` `text-primary`，单行截断
  - 作者：`text-xs` `text-secondary`
  - 价格：`text-base` `text-error` `font-bold`
  - 销量标签：`text-xs` `text-secondary`

**空状态**：
- 页面中央展示 120×120px 空状态插画
- 文案「暂无商品」`text-base` `text-secondary`，下方间距 `spacing-lg`
- 「去首页看看」按钮：Button-Secondary，居中

**错误状态**：
- 页面中央展示 80×80px 错误图标 `neutral-400`
- 文案「加载失败，点击重试」`text-sm` `text-secondary`
- 重试按钮：Button-Text

### 4.2 P002 商品详情

**默认状态**：
- 商品大图轮播：宽度 100%，高度 375px，底部指示器小圆点
- 价格区：左对齐，`spacing-md` 内边距
  - 现价：`text-2xl` `text-error` `font-bold`
  - 原价：`text-sm` `text-secondary`，中划线
  - 促销标签：`text-xs` `text-inverse` `bg-error` `radius-sm` 内边距
- 基本信息区：
  - 书名：`text-lg` `text-primary` `font-bold`
  - 作者/出版社：`text-sm` `text-secondary`
  - 评分：星星图标 + `text-sm` `text-warning`
- 底部操作栏：高度 56px，固定底部，安全区适配
  - 「加入购物车」：左侧，Button-Secondary，宽度 40%
  - 「立即购买」：右侧，Button-Primary，宽度 60%

**空状态（商品下架）**：
- 中央插画 + 「商品已下架」`text-base`
- 「返回」按钮：Button-Secondary

### 4.3 P003 购物车

**默认状态**：
- 商品项：高度 100px，左对齐选择框（24×24px），右侧商品信息
  - 封面缩略图：60×80px，`radius-sm`
  - 书名：`text-sm` `text-primary`，两行截断
  - 单价：`text-sm` `text-error`
  - 步进器：右对齐
- 底部结算栏：高度 56px，固定底部
  - 左侧：全选复选框 + 「全选」文案
  - 右侧：「合计：¥xxx」`text-sm` + 「去结算」Button-Primary

**空状态**：
- 中央插画 + 「购物车是空的」`text-base` `text-secondary`
- 「去逛逛」Button-Primary

### 4.4 P004 订单确认

**默认状态**：
- 收货地址卡片：高度自适应，最小 72px，`bg-surface` `radius-lg` `spacing-md` 外边距
  - 收件人：`text-sm` `text-primary` `font-bold`
  - 电话：`text-sm` `text-secondary`
  - 地址：`text-sm` `text-primary`
  - 右箭头：`neutral-400`，24×24px
- 商品清单区：店铺名 `text-sm` `font-bold`，商品项同购物车样式但不可编辑数量
- 金额明细区：
  - 商品总额：`text-sm` `text-secondary`，右对齐
  - 运费：`text-sm` `text-secondary`，右对齐
  - 实付金额：`text-lg` `text-error` `font-bold`，右对齐
- 支付方式：单选列表，选中项右侧展示 `primary-500` 对勾图标
- 底部提交栏：固定底部，「实付 ¥xxx」左对齐 + 「提交订单」Button-Primary 右对齐

**地址缺失状态**：
- 地址卡片显示「请添加收货地址」`text-sm` `text-primary`，中央加号图标

### 4.5 P005 订单列表

**默认状态**：
- 状态筛选栏：同 P001 分类筛选栏样式
- 订单卡片：`bg-surface` `radius-lg` `shadow-sm` `spacing-md` 外边距
  - 顶部：店铺名左对齐 + 状态标签右对齐
  - 中部：商品缩略图横向排列，最多 3 个，每个 60×60px `radius-sm`，超出显示「+n」灰色方块
  - 底部：「共 n 件 合计：¥xxx」`text-sm` `text-secondary` + 操作按钮区
- 操作按钮根据状态变化：
  - PENDING：「取消订单」Button-Text + 「立即支付」Button-Primary-small
  - SHIPPED：「查看物流」Button-Text + 「确认收货」Button-Primary-small

**空状态**：同 P001 空状态样式，文案改为「暂无订单」

### 4.6 P006 订单详情

**默认状态**：
- 订单状态区：页面顶部，高度 80px，渐变背景 `primary-500` → `primary-600`
  - 状态图标：48×48px，白色
  - 状态文案：`text-lg` `text-inverse` `font-bold`
  - 状态说明：`text-sm` `text-inverse` `opacity-80`
- 物流信息区（SHIPPED 及以上）：`bg-surface` `radius-lg` 卡片
  - 物流公司/单号：`text-sm` `text-secondary`
  - 最新节点：`text-sm` `text-primary` `font-medium`
- 商品清单：同 P004 商品清单样式
- 金额明细：同 P004 金额明细样式
- 订单信息：标签 `text-secondary` `text-xs`，值 `text-primary` `text-sm`
- 底部操作栏：根据状态动态变化，按钮样式参见 P005

**错误状态（无权查看）**：
- 中央错误图标 + 「您无权查看此订单」`text-base`
- 「返回首页」Button-Secondary
