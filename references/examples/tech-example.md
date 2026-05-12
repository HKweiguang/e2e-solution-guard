# TECH-v1-订单服务

**覆盖功能点**：F001, F002, F003, F004, F005, F006
**版本号**：v1.0.0
**制定日期**：2024-01-15
**作者**：示例团队

**上游文档**：

| 文档 | 类型 | 引用范围 |
|------|------|---------|
| PRD-v1-订单模块 | 需求输入 | F001-F006 |
| 交互设计-订单交易流程 | 设计输入 | P001-P006 |
| 项目技术-顶层定义 | 规范继承 | 技术栈、公共表、接口约定 |

---

## §1 关联文档

| 文档 | 链接 |
|------|------|
| PRD-v1-订单模块 | `/docs/prd/PRD-v1-订单模块.md` |
| 交互设计-订单交易流程 | `/docs/interaction/交互设计-订单交易流程.md` |
| 项目技术-顶层定义 | `/docs/tech/项目技术-顶层定义.md` |

---

## §2 服务概述

订单服务（order-service）负责用户购书交易全链路的订单生命周期管理，包括订单创建、状态流转、查询和取消。

**覆盖范围**：
- 订单创建与提交（F003）
- 订单状态管理：PENDING → PAID → SHIPPED → COMPLETED / CANCELLED（F004-F006）
- 订单查询：列表与详情（F005）
- 购物车数据管理（F002）

**不覆盖范围**：
- 商品信息查询（由商品服务提供）
- 支付处理（由支付服务提供，本服务仅接收回调）
- 物流跟踪（由物流服务提供，本服务仅展示物流单号）

**关键技术决策**：
- 订单号采用业务单号（ORD前缀）而非自增ID，避免枚举攻击
- 订单状态变更采用状态机模式，禁止跨状态跳转
- 库存校验在订单创建时同步完成，支付回调时二次校验金额

---

## §3 技术实现要点

| 决策编号 | 决策项 | 选型 | 理由 | 备选方案 |
|---------|--------|------|------|---------|
| D001 | 订单号生成策略 | 业务单号（ORD+时间戳+6位随机数） | 可读性强，避免自增ID被遍历 | UUID（可读性差） |
| D002 | 库存校验时机 | 下单时同步校验 + 支付回调时二次校验 | 防止超卖，双重保障 | 仅异步校验（存在超卖风险） |
| D003 | 订单状态持久化 | 状态字段 + 状态变更日志表 | 可追溯状态变更历史，便于审计 | 仅状态字段（无法追溯） |
| D004 | 购物车存储 | Redis Hash，TTL 30 天 | 高性能读写，自动过期清理 | 数据库表（写频繁，性能差） |

---

## §4 依赖关系

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| product-service | 服务依赖 | 查询商品信息、校验库存 |
| payment-service | 服务依赖 | 发起支付请求、接收支付回调 |
| logistics-service | 服务依赖 | 获取物流轨迹（查询时调用） |
| user-service | 服务依赖 | 查询用户收货地址 |
| redis | 基础设施 | 购物车数据存储 |
| mysql | 基础设施 | 订单主数据存储 |

---

## §5 数据模型

### 5.1 订单表（t_order）

| 字段 | 类型 | 约束 | 对应 PRD 字段 | 说明 |
|------|------|------|-------------|------|
| id | BIGINT | PK, AUTO_INCREMENT | — | 自增主键 |
| order_no | VARCHAR(32) | UK, NOT NULL | order_id | 业务单号 |
| user_id | VARCHAR(32) | NOT NULL, INDEX | user_id | 用户ID |
| total_amount | DECIMAL(10,2) | NOT NULL | total_amount | 订单总金额 |
| status | VARCHAR(16) | NOT NULL, INDEX | status | 订单状态 |
| pay_method | VARCHAR(16) | — | pay_method | 支付方式 |
| receiver_address | VARCHAR(256) | NOT NULL | receiver_address | 收货地址 |
| created_at | DATETIME | NOT NULL | created_at | 创建时间 |
| updated_at | DATETIME | NOT NULL | updated_at | 更新时间 |
| created_by | VARCHAR(32) | NOT NULL | — | 创建人 |
| updated_by | VARCHAR(32) | NOT NULL | — | 更新人 |

```sql
CREATE TABLE t_order (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    order_no VARCHAR(32) NOT NULL UNIQUE COMMENT '业务单号',
    user_id VARCHAR(32) NOT NULL COMMENT '用户ID',
    total_amount DECIMAL(10,2) NOT NULL COMMENT '订单总金额',
    status VARCHAR(16) NOT NULL COMMENT '订单状态：PENDING/PAID/SHIPPED/COMPLETED/CANCELLED',
    pay_method VARCHAR(16) COMMENT '支付方式',
    receiver_address VARCHAR(256) NOT NULL COMMENT '收货地址',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(32) NOT NULL COMMENT '创建人',
    updated_by VARCHAR(32) NOT NULL COMMENT '更新人',
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) COMMENT='订单主表';
```

### 5.2 订单项表（t_order_item）

| 字段 | 类型 | 约束 | 对应 PRD 字段 | 说明 |
|------|------|------|-------------|------|
| id | BIGINT | PK, AUTO_INCREMENT | — | 自增主键 |
| order_id | BIGINT | FK, NOT NULL | order_id | 关联订单ID |
| book_id | VARCHAR(32) | NOT NULL | book_id | 书籍ID |
| book_title | VARCHAR(128) | NOT NULL | book_title | 书籍标题快照 |
| quantity | INT | NOT NULL | quantity | 购买数量 |
| unit_price | DECIMAL(10,2) | NOT NULL | unit_price | 单价 |
| subtotal | DECIMAL(10,2) | NOT NULL | subtotal | 小计金额 |
| created_at | DATETIME | NOT NULL | — | 创建时间 |
| updated_at | DATETIME | NOT NULL | — | 更新时间 |
| created_by | VARCHAR(32) | NOT NULL | — | 创建人 |
| updated_by | VARCHAR(32) | NOT NULL | — | 更新人 |

```sql
CREATE TABLE t_order_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    order_id BIGINT NOT NULL COMMENT '关联订单ID',
    book_id VARCHAR(32) NOT NULL COMMENT '书籍ID',
    book_title VARCHAR(128) NOT NULL COMMENT '书籍标题快照',
    quantity INT NOT NULL COMMENT '购买数量',
    unit_price DECIMAL(10,2) NOT NULL COMMENT '单价',
    subtotal DECIMAL(10,2) NOT NULL COMMENT '小计金额',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(32) NOT NULL COMMENT '创建人',
    updated_by VARCHAR(32) NOT NULL COMMENT '更新人',
    FOREIGN KEY (order_id) REFERENCES t_order(id)
) COMMENT='订单项表';
```

### 5.3 订单状态变更日志表（t_order_status_log）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 自增主键 |
| order_id | BIGINT | NOT NULL, INDEX | 关联订单ID |
| old_status | VARCHAR(16) | NOT NULL | 变更前状态 |
| new_status | VARCHAR(16) | NOT NULL | 变更后状态 |
| operator | VARCHAR(32) | NOT NULL | 操作人（SYSTEM/USER_ID） |
| reason | VARCHAR(256) | — | 变更原因 |
| created_at | DATETIME | NOT NULL | 变更时间 |

```sql
CREATE TABLE t_order_status_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL COMMENT '关联订单ID',
    old_status VARCHAR(16) NOT NULL COMMENT '变更前状态',
    new_status VARCHAR(16) NOT NULL COMMENT '变更后状态',
    operator VARCHAR(32) NOT NULL COMMENT '操作人',
    reason VARCHAR(256) COMMENT '变更原因',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '变更时间',
    INDEX idx_order_id (order_id)
) COMMENT='订单状态变更日志';
```

---

## §6 接口设计

### 6.1 接口汇总

| 接口 | 方法 | 路径 | 对应功能点 |
|------|------|------|-----------|
| 提交订单 | POST | /api/v1/orders | F003 |
| 查询订单列表 | GET | /api/v1/orders | F005 |
| 查询订单详情 | GET | /api/v1/orders/{orderNo} | F005 |
| 取消订单 | POST | /api/v1/orders/{orderNo}/cancel | F006 |
| 支付回调 | POST | /api/v1/orders/pay-callback | F004 |

### 6.2 提交订单

**URL**：`POST /api/v1/orders`

**功能**：从购物车或立即购买创建订单。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| bookItems | Array | 是 | 商品项列表 |
| bookItems[].bookId | String | 是 | 书籍ID |
| bookItems[].quantity | Integer | 是 | 购买数量 |
| receiverAddressId | String | 是 | 收货地址ID |
| payMethod | String | 是 | 支付方式：WECHAT/ALIPAY/CARD |

**响应结构**：

```json
{
  "code": "SUCCESS",
  "message": "ok",
  "data": {
    "orderNo": "ORD202401151200001",
    "totalAmount": 128.50,
    "status": "PENDING",
    "createdAt": "2024-01-15T12:00:00+08:00"
  }
}
```

**错误码**：

| 错误码 | 触发场景 |
|--------|---------|
| E001 | 库存不足 |
| E004 | 无权操作（地址不属于当前用户） |

### 6.3 查询订单列表

**URL**：`GET /api/v1/orders`

**功能**：查询当前用户的订单列表，支持按状态筛选。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | String | 否 | 状态筛选：PENDING/PAID/SHIPPED/COMPLETED/CANCELLED |
| page | Integer | 否 | 页码，默认1 |
| pageSize | Integer | 否 | 每页数量，默认10 |

**响应结构**：

```json
{
  "code": "SUCCESS",
  "message": "ok",
  "data": {
    "list": [
      {
        "orderNo": "ORD202401151200001",
        "totalAmount": 128.50,
        "status": "PENDING",
        "itemCount": 2,
        "createdAt": "2024-01-15T12:00:00+08:00"
      }
    ],
    "total": 15,
    "page": 1,
    "pageSize": 10
  }
}
```

### 6.4 查询订单详情

**URL**：`GET /api/v1/orders/{orderNo}`

**功能**：查询单个订单的完整信息。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| orderNo | String | 订单编号 |

**响应结构**：

```json
{
  "code": "SUCCESS",
  "message": "ok",
  "data": {
    "orderNo": "ORD202401151200001",
    "userId": "U123456",
    "totalAmount": 128.50,
    "status": "PENDING",
    "payMethod": "WECHAT",
    "receiverAddress": "北京市海淀区xxx街道xxx号",
    "items": [
      {
        "bookId": "B001",
        "bookTitle": "示例书籍",
        "quantity": 2,
        "unitPrice": 64.25,
        "subtotal": 128.50
      }
    ],
    "createdAt": "2024-01-15T12:00:00+08:00",
    "updatedAt": "2024-01-15T12:00:00+08:00"
  }
}
```

**错误码**：

| 错误码 | 触发场景 |
|--------|---------|
| E002 | 订单不存在 |
| E004 | 无权查看（非订单所有者） |

### 6.5 取消订单

**URL**：`POST /api/v1/orders/{orderNo}/cancel`

**功能**：取消待支付订单。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| orderNo | String | 订单编号 |

**错误码**：

| 错误码 | 触发场景 |
|--------|---------|
| E002 | 订单不存在 |
| E004 | 无权操作 |
| E005 | 订单状态不允许取消（非 PENDING） |

### 6.6 支付回调

**URL**：`POST /api/v1/orders/pay-callback`

**功能**：接收支付服务的结果回调，更新订单状态。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| orderNo | String | 是 | 订单编号 |
| payAmount | Decimal | 是 | 实际支付金额 |
| payStatus | String | 是 | 支付结果：SUCCESS/FAIL |
| transactionId | String | 是 | 支付流水号 |

**错误码**：

| 错误码 | 触发场景 |
|--------|---------|
| E002 | 订单不存在 |
| E003 | 支付金额与订单金额不一致 |

---

## §7 核心流程

### 7.1 提交订单流程

```
用户 → [提交订单接口]
           ↓
      校验用户登录态
           ↓
      校验收货地址归属
           ↓
      遍历商品项 → 调用商品服务校验库存
           ↓
      计算订单总金额
           ↓
      创建订单（t_order）
           ↓
      创建订单项（t_order_item）
           ↓
      扣减库存（调用商品服务）
           ↓
      记录状态日志（PENDING）
           ↓
      返回订单信息
```

### 7.2 支付回调流程

```
支付服务 → [支付回调接口]
              ↓
         校验签名
              ↓
         查询订单
              ↓
         校验支付金额 = 订单金额
              ↓
         更新订单状态：PENDING → PAID
              ↓
         记录状态日志
              ↓
         异步通知物流服务发货
              ↓
         返回成功
```

---

## §8 异常处理

| 异常编号 | 场景 | 触发条件 | 技术处理 | 用户提示 |
|---------|------|---------|---------|---------|
| EX001 | 库存不足 | 提交订单时商品库存 < 购买数量 | 事务回滚，订单不创建 | 商品库存不足，请减少数量 |
| EX002 | 订单不存在 | 查询/取消/回调时订单号无效 | 返回 404 + E002 | 订单不存在 |
| EX003 | 金额不一致 | 支付回调金额 ≠ 订单金额 | 记录异常日志，触发退款流程 | 支付异常，已发起退款 |
| EX004 | 并发取消 | 两个请求同时取消同一订单 | 数据库乐观锁（version 字段），只有一个成功 | — |
| EX005 | 重复支付回调 | 同一笔订单收到多次支付成功回调 | 幂等校验：PAID 状态不再处理 | — |

---

## §9 性能与安全

### 9.1 性能优化

| 优化点 | 方案 |
|--------|------|
| 订单列表查询 | 按 user_id + status 联合索引，分页查询 |
| 订单详情查询 | 按 order_no 唯一索引，单次查询 |
| 热点库存 | 商品服务使用 Redis 预扣库存，异步同步数据库 |

### 9.2 安全设计

| 安全项 | 方案 |
|--------|------|
| 接口权限 | 所有接口需登录（JWT Token），查询类接口校验数据归属 |
| 支付回调安全 | 回调接口校验支付服务签名，防止伪造回调 |
| 金额精度 | 使用 Decimal 类型，禁止浮点数计算 |

---

## §10 接口清单

| 接口 | 方法 | 路径 | 对应功能点 | 权限 |
|------|------|------|-----------|------|
| 提交订单 | POST | /api/v1/orders | F003 | 登录用户 |
| 查询订单列表 | GET | /api/v1/orders | F005 | 登录用户 |
| 查询订单详情 | GET | /api/v1/orders/{orderNo} | F005 | 登录用户（数据归属校验） |
| 取消订单 | POST | /api/v1/orders/{orderNo}/cancel | F006 | 登录用户（数据归属校验） |
| 支付回调 | POST | /api/v1/orders/pay-callback | F004 | 内部服务（签名校验） |
