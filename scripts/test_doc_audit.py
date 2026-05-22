#!/usr/bin/env python3
"""doc-audit.py 冒烟测试"""

import subprocess, json, tempfile, os

def run_audit(doc_path, doc_type, upstream_paths=None, top_level_paths=None):
    cmd = ["python3", "scripts/doc-audit.py", doc_path, "--type", doc_type]
    if upstream_paths:
        for up in upstream_paths:
            cmd.extend(["--upstream", up])
    if top_level_paths:
        for tl in top_level_paths:
            cmd.extend(["--top-level", tl])
    return json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)

def test_bidirectional_mapping():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| FP-001 | A |\n| FP-002 | B |\n""")
        prd = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n**覆盖功能点**：FP-001, FP-003\n\n## §4 接口设计\n| 对应功能点 |\n|-----------|\n| FP-001 |\n""")
        tech = f.name
    try:
        r = run_audit(tech, "tech", [prd])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-B1"]
        assert any("FP-002" in m and "无对应引用" in m for m in msgs)
        assert any("FP-003" in m and "不存在" in m for m in msgs)
        print("✅ test_bidirectional_mapping")
    finally:
        os.unlink(prd); os.unlink(tech)

def test_cross_doc_terminology():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义\n\n## §4 术语表\n| 术语 | 禁止别名 |\n|------|---------|\n| 工单 | 不可称"任务单" |\n""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD-模块\n\n## §3 功能需求\n用户创建任务单。\n""")
        mod = f.name
    try:
        r = run_audit(mod, "prd", [top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B2"]
        assert any("任务单" in m for m in msgs)
        print("✅ test_cross_doc_terminology")
    finally:
        os.unlink(top); os.unlink(mod)

def test_broken_internal_link():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Doc\n\n## §1 A\n参见 §1。\n\n## §2 B\n参见 §5。\n""")
        path = f.name
    try:
        r = run_audit(path, "prd")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-A16"]
        assert any("§5" in m for m in msgs)
        assert not any("§1" in m for m in msgs)
        print("✅ test_broken_internal_link")
    finally:
        os.unlink(path)

def test_responsive_breakpoint():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='ui-top-level-', delete=False) as f:
        f.write("""# UI-Top\n\n## §2.5.5 响应式断点\n| 断点名 | 范围 |\n|--------|------|\n| 手机 | < 768px |\n| 桌面 | ≥ 1024px |\n""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html><html><head><style>
        @media (max-width: 768px) { .a { width:100%; } }
        </style></head><body></body></html>""")
        html = f.name
    try:
        r = run_audit(html, "ui", [top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "U-B5"]
        assert any("1024" in m for m in msgs)
        assert not any("768" in m for m in msgs)
        print("✅ test_responsive_breakpoint")
    finally:
        os.unlink(top); os.unlink(html)

def test_reverse_feature_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| FP-001 | A |\n\n## §6 业务规则\n规则1：当 FP-002 触发时...\n\n## §7 错误处理\nERR-001：当 FP-003 触发时...\n""")
        path = f.name
    try:
        r = run_audit(path, "prd")
        assert any("FP-002" in i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-A8")
        assert any("FP-003" in i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-A10")
        print("✅ test_reverse_feature_ref")
    finally:
        os.unlink(path)

def test_interface_inventory_match():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §4 接口设计\n### 4.1 创建\n| URL | `POST /api/tickets` |\n| 功能 | 创建工单 |\n\n## §13 接口清单\n| 序号 | 接口名 | 方法 | 路径 |\n|------|--------|------|------|\n| 1 | 查询 | GET | /api/tickets |\n""")
        path = f.name
    try:
        r = run_audit(path, "tech")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-A9"]
        assert any("POST /api/tickets" in m for m in msgs)
        assert any("GET /api/tickets" in m for m in msgs)
        print("✅ test_interface_inventory_match")
    finally:
        os.unlink(path)

def test_page_structure():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# 交互设计-v1-首页\n\n# 首页\n## 页面结构\n## 组件交互\n## 状态机\n## 页面流程\n## 异常处理\n## 与 PRD 对应\n\n# 列表页\n## 页面结构\n## 组件交互\n""")
        path = f.name
    try:
        r = run_audit(path, "interaction")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "I-A2"]
        assert any("列表页" in m and "状态机" in m for m in msgs)
        assert not any("首页" in m for m in msgs)
        print("✅ test_page_structure")
    finally:
        os.unlink(path)

def test_table_field_interface_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §3 数据模型\n| 字段名 | 类型 |\n|--------|------|\n| user_id | BIGINT |\n| ticket_title | VARCHAR |\n\n## §4 接口设计\n| URL | `POST /api/tickets` |\n| 请求参数 | user_id |\n""")
        path = f.name
    try:
        r = run_audit(path, "tech")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-A10"]
        assert any("ticket_title" in m for m in msgs)
        assert not any("user_id" in m for m in msgs)
        print("✅ test_table_field_interface_ref")
    finally:
        os.unlink(path)

def test_exception_interface_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §4 接口设计\n错误码：ERR-TICKET-001\n\n## §7 异常处理\nERR-TICKET-001：网络错误\nERR-TICKET-002：权限不足\n""")
        path = f.name
    try:
        r = run_audit(path, "tech")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-A11"]
        assert any("ERR-TICKET-002" in m for m in msgs)
        assert not any("ERR-TICKET-001" in m for m in msgs)
        print("✅ test_exception_interface_ref")
    finally:
        os.unlink(path)

def test_test_case_feature_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test\n\n## §1 功能测试用例\n| 用例编号 | 用例名称 | 功能点 | 验收标准 |\n|---------|---------|--------|---------|\n| TC-001 | 登录 | FP-001 | AC-001 |\n| TC-002 | 注册 | — | — |\n""")
        path = f.name
    try:
        r = run_audit(path, "test")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-A3"]
        assert any("TC-002" in m and "功能点编号" in m for m in msgs)
        assert any("TC-002" in m and "验收标准编号" in m for m in msgs)
        print("✅ test_test_case_feature_ref")
    finally:
        os.unlink(path)

def test_test_exception_coverage():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test\n\n## §2 异常测试用例\n参数非法、权限不足、数据不存在\n""")
        path = f.name
    try:
        r = run_audit(path, "test")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-A4"]
        assert any("网络异常" in m for m in msgs)
        print("✅ test_test_exception_coverage")
    finally:
        os.unlink(path)

# --- 本轮新增测试 ---

def test_id_format_consistency():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| USER-001 | A |\n| ORDER-001 | B |\n""")
        path = f.name
    try:
        r = run_audit(path, "prd")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-A5"]
        assert any("USER" in m and "ORDER" in m for m in msgs)
        print("✅ test_id_format_consistency")
    finally:
        os.unlink(path)

def test_page_prefix_consistency():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# 交互设计\n\n# PAGE-PROFILE-001 个人中心\n## 页面结构\n\n# PAGE-LIST-001 列表\n## 页面结构\n\n# PAGE-ORDER-001 订单\n## 页面结构\n""")
        path = f.name
    try:
        r = run_audit(path, "interaction")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "I-B1"]
        # 页面编号前缀统一为 PAGE，不应报错
        assert len(msgs) == 0, f"不应报告前缀不一致: {msgs}"
        print("✅ test_page_prefix_consistency")
    finally:
        os.unlink(path)

def test_page_prefix_inconsistency():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# 交互设计\n\n# PAGE-PROFILE-001 个人中心\n## 页面结构\n\n# PANEL-SETTINGS-001 设置\n## 页面结构\n""")
        path = f.name
    try:
        r = run_audit(path, "interaction")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "I-B1"]
        assert any("PAGE" in m and "PANEL" in m for m in msgs)
        print("✅ test_page_prefix_inconsistency")
    finally:
        os.unlink(path)

def test_page_coverage():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='interaction-', delete=False) as f:
        f.write("""# 交互设计\n\n# PAGE-PROFILE-001 个人中心\n## 页面结构\n\n# PAGE-LIST-001 列表\n## 页面结构\n""")
        inter = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html><html><body>
        <section id="PAGE-PROFILE-001"></section>
        </body></html>""")
        html = f.name
    try:
        r = run_audit(html, "ui", [inter])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "U-B1"]
        assert any("PAGE-LIST-001" in m for m in msgs)
        assert not any("PAGE-PROFILE-001" in m for m in msgs)
        print("✅ test_page_coverage")
    finally:
        os.unlink(inter); os.unlink(html)

def test_table_column_completeness():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §3 数据模型\n| 字段名 | 类型 |\n|--------|------|\n| id | BIGINT |\n\n| 字段名 | 类型 | 约束 | 索引 |\n|--------|------|------|------|\n| name | VARCHAR | NOT NULL | idx_name |\n""")
        path = f.name
    try:
        r = run_audit(path, "tech")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-A3"]
        assert any("约束" in m for m in msgs)
        assert any("索引" in m for m in msgs)
        print("✅ test_table_column_completeness")
    finally:
        os.unlink(path)

def test_interface_test_coverage():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='tech-', delete=False) as f:
        f.write("""# Tech\n\n## §13 接口清单\n| 序号 | 接口名 | 方法 | 路径 |\n|------|--------|------|------|\n| 1 | 创建 | POST | /api/tickets |\n| 2 | 查询 | GET | /api/tickets |\n""")
        tech = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test\n\n## §1 功能测试用例\n测试 POST /api/tickets\n""")
        test = f.name
    try:
        r = run_audit(test, "test", [tech])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-B5"]
        assert any("GET /api/tickets" in m for m in msgs)
        assert not any("POST /api/tickets" in m for m in msgs)
        print("✅ test_interface_test_coverage")
    finally:
        os.unlink(tech); os.unlink(test)

# --- 本轮新增测试 ---

def test_top_level_state_value():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义

## §5 状态值
| 字段名 | 状态值 | 说明 |
|--------|--------|------|
| 工单状态 | PENDING | 待处理 |
| 工单状态 | CLOSED | 已关闭 |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §6 业务规则
当工单状态为 PENDING 时...
当工单状态为 UNKNOWN 时...
""")
        prd = f.name
    try:
        r = run_audit(prd, "prd", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B1"]
        assert any("UNKNOWN" in m for m in msgs)
        assert not any("PENDING" in m for m in msgs)
        print("✅ test_top_level_state_value")
    finally:
        os.unlink(top); os.unlink(prd)

def test_top_level_error_code_format():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义

## §6 编码规则
| 编码类型 | 前缀 |
|---------|------|
| 错误码 | ERR |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §7 错误处理
| 错误码 | 触发场景 |
|--------|---------|
| ERR-001 | 网络错误 |
| BAD-001 | 参数错误 |
""")
        prd = f.name
    try:
        r = run_audit(prd, "prd", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B6"]
        assert any("BAD-001" in m for m in msgs)
        assert not any("ERR-001" in m for m in msgs)
        print("✅ test_top_level_error_code_format")
    finally:
        os.unlink(top); os.unlink(prd)

def test_top_level_id_prefix():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义

## §6 编码规则
| 编码类型 | 前缀 |
|---------|------|
| 功能编号 | USER |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §3 功能需求
| 功能编号 | 名称 |
|---------|------|
| USER-001 | A |
| ORDER-001 | B |
""")
        prd = f.name
    try:
        r = run_audit(prd, "prd", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B2"]
        assert any("ORDER-001" in m for m in msgs)
        assert not any("USER-001" in m for m in msgs)
        print("✅ test_top_level_id_prefix")
    finally:
        os.unlink(top); os.unlink(prd)

def test_top_level_enum():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义

## §5 状态值
| 字段名 | 状态值 |
|--------|--------|
| 状态 | ACTIVE |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §5 数据模型
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| status | VARCHAR | ENUM('ACTIVE','INACTIVE','UNKNOWN') | 状态 |
""")
        prd = f.name
    try:
        r = run_audit(prd, "prd", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B7"]
        assert any("'UNKNOWN'" in m for m in msgs)
        assert not any("'ACTIVE'" in m for m in msgs)
        print("✅ test_top_level_enum")
    finally:
        os.unlink(top); os.unlink(prd)

def test_ui_top_level_token():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='ui-top-level-', delete=False) as f:
        f.write("""# UI-顶层定义

## §3 Token
| Token | 用途 |
|-------|------|
| --color-primary | 主色 |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html><html><head><style>
        :root { --color-primary: #1890ff; --custom-red: #ff0000; }
        </style></head><body></body></html>""")
        html = f.name
    try:
        r = run_audit(html, "ui", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "U-B4"]
        assert any("custom-red" in m for m in msgs)
        assert not any("color-primary" in m for m in msgs)
        print("✅ test_ui_top_level_token")
    finally:
        os.unlink(top); os.unlink(html)

def test_tech_top_level_field_naming():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §3 数据模型
| 字段名 | 类型 |
|--------|------|
| userId | BIGINT |
| create_time | DATETIME |
""")
        tech = f.name
    try:
        r = run_audit(tech, "tech")
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-A14"]
        assert any("userId" in m for m in msgs)
        assert not any("create_time" in m for m in msgs)
        print("✅ test_tech_top_level_field_naming")
    finally:
        os.unlink(tech)

def test_test_top_level_case_id():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='test-top-level-', delete=False) as f:
        f.write("""# Test-顶层定义

## §6 编码规则
| 编码类型 | 前缀 |
|---------|------|
| 用例编号 | TC |
""")
        top = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test

## §1 功能测试用例
| 用例编号 | 名称 |
|---------|------|
| TC-001 | A |
| CASE-001 | B |
""")
        test = f.name
    try:
        r = run_audit(test, "test", top_level_paths=[top])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-B1"]
        assert any("CASE-001" in m for m in msgs)
        assert not any("TC-001" in m for m in msgs)
        print("✅ test_test_top_level_case_id")
    finally:
        os.unlink(top); os.unlink(test)

def test_prd_error_code_to_tech():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §7 错误处理
| 错误码 | 触发场景 |
|--------|---------|
| ERR-001 | 网络错误 |
| ERR-002 | 权限不足 |
""")
        prd = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §7 异常处理
| 错误码 | 场景 |
|--------|------|
| ERR-001 | 网络错误 |
""")
        tech = f.name
    try:
        r = run_audit(tech, "tech", upstream_paths=[prd])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-B8"]
        assert any("ERR-002" in m for m in msgs)
        assert not any("ERR-001" in m for m in msgs)
        print("✅ test_prd_error_code_to_tech")
    finally:
        os.unlink(prd); os.unlink(tech)

def test_prd_entity_to_tech_table():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §5 数据模型
| 实体 | 说明 |
|------|------|
| 用户 | 用户信息 |
| 订单 | 订单信息 |
""")
        prd = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §3 数据模型
### 用户表
| 字段名 | 类型 |
|--------|------|
| id | BIGINT |
""")
        tech = f.name
    try:
        r = run_audit(tech, "tech", upstream_paths=[prd])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "T-B9"]
        assert any("订单" in m for m in msgs)
        assert not any("用户" in m for m in msgs)
        print("✅ test_prd_entity_to_tech_table")
    finally:
        os.unlink(prd); os.unlink(tech)

def test_tech_exception_to_test():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §7 异常处理
| 异常编号 | 错误码 |
|---------|--------|
| EX-001 | ERR-001 |
| EX-002 | ERR-002 |
""")
        tech = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test

## §2 异常测试用例
| 错误码 | 场景 |
|--------|------|
| ERR-001 | 网络错误 |
""")
        test = f.name
    try:
        r = run_audit(test, "test", upstream_paths=[tech])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-B13"]
        assert any("EX-002" in m for m in msgs)
        assert any("ERR-002" in m for m in msgs)
        assert not any("ERR-001" in m for m in msgs)
        print("✅ test_tech_exception_to_test")
    finally:
        os.unlink(tech); os.unlink(test)

def test_tech_interface_to_test():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §13 接口清单
| 序号 | 接口名 | 方法 | 路径 |
|------|--------|------|------|
| 1 | 创建 | POST | /api/tickets |
| 2 | 查询 | GET | /api/users |
""")
        tech = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test

## §1 功能测试用例
测试 POST /api/tickets
""")
        test = f.name
    try:
        r = run_audit(test, "test", upstream_paths=[tech])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "S-B14"]
        assert any("/api/users" in m for m in msgs)
        assert not any("/api/tickets" in m for m in msgs)
        print("✅ test_tech_interface_to_test")
    finally:
        os.unlink(tech); os.unlink(test)

def test_error_code_count_match():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD

## §7 错误处理
| 错误码 | 触发场景 |
|--------|---------|
| ERR-001 | 网络错误 |
| ERR-002 | 权限不足 |
""")
        prd = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech

## §7 异常处理
| 错误码 | 场景 |
|--------|------|
| ERR-001 | 网络错误 |
| ERR-002 | 权限不足 |
""")
        tech = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test

## §2 异常测试用例
| 错误码 | 场景 |
|--------|------|
| ERR-001 | 网络错误 |
""")
        test = f.name
    try:
        r = run_audit(prd, "prd", upstream_paths=[tech, test])
        msgs = [i["message"] for i in r["mechanical_issues"] if i["check_id"] == "P-B8"]
        assert any("2" in m and "1" in m for m in msgs)
        print("✅ test_error_code_count_match")
    finally:
        os.unlink(prd); os.unlink(tech); os.unlink(test)

if __name__ == "__main__":
    test_bidirectional_mapping()
    test_cross_doc_terminology()
    test_broken_internal_link()
    test_responsive_breakpoint()
    test_reverse_feature_ref()
    test_interface_inventory_match()
    test_page_structure()
    test_table_field_interface_ref()
    test_exception_interface_ref()
    test_test_case_feature_ref()
    test_test_exception_coverage()
    test_id_format_consistency()
    test_page_prefix_consistency()
    test_page_prefix_inconsistency()
    test_page_coverage()
    test_table_column_completeness()
    test_interface_test_coverage()
    test_top_level_state_value()
    test_top_level_error_code_format()
    test_top_level_id_prefix()
    test_top_level_enum()
    test_ui_top_level_token()
    test_tech_top_level_field_naming()
    test_test_top_level_case_id()
    test_prd_error_code_to_tech()
    test_prd_entity_to_tech_table()
    test_tech_exception_to_test()
    test_tech_interface_to_test()
    test_error_code_count_match()
    print("\n🎉 All tests passed!")
