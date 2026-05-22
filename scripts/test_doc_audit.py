#!/usr/bin/env python3
"""doc-audit.py 冒烟测试：验证规则基本功能"""

import subprocess
import json
import tempfile
import os

def run_audit(doc_path, doc_type, upstream_paths=None):
    cmd = ["python3", "scripts/doc-audit.py", doc_path, "--type", doc_type]
    if upstream_paths:
        for up in upstream_paths:
            cmd.extend(["--upstream", up])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

def test_bidirectional_mapping():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| FP-001 | A |\n| FP-002 | B |\n""")
        prd_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n**覆盖功能点**：FP-001, FP-003\n\n## §4 接口设计\n| 对应功能点 |\n|-----------|\n| FP-001 |\n""")
        tech_path = f.name
    try:
        result = run_audit(tech_path, "tech", [prd_path])
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "T-B1"]
        assert any("FP-002" in m and "无对应引用" in m for m in msgs), f"正向失败: {msgs}"
        assert any("FP-003" in m and "不存在" in m for m in msgs), f"反向失败: {msgs}"
        print("✅ test_bidirectional_mapping")
    finally:
        os.unlink(prd_path); os.unlink(tech_path)

def test_cross_doc_terminology():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义\n\n## §4 术语表\n| 术语 | 禁止别名 |\n|------|---------|\n| 工单 | 不可称"任务单" |\n""")
        top_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD-模块\n\n## §3 功能需求\n用户创建任务单。\n""")
        mod_path = f.name
    try:
        result = run_audit(mod_path, "prd", [top_path])
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-B2"]
        assert any("任务单" in m for m in msgs), f"术语失败: {msgs}"
        print("✅ test_cross_doc_terminology")
    finally:
        os.unlink(top_path); os.unlink(mod_path)

def test_broken_internal_link():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Doc\n\n## §1 A\n参见 §1。\n\n## §2 B\n参见 §5。\n""")
        path = f.name
    try:
        result = run_audit(path, "prd")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-A16"]
        assert any("§5" in m for m in msgs), f"断裂链接失败: {msgs}"
        assert not any("§1" in m for m in msgs), f"不应报告存在的链接: {msgs}"
        print("✅ test_broken_internal_link")
    finally:
        os.unlink(path)

def test_responsive_breakpoint():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='ui-top-level-', delete=False) as f:
        f.write("""# UI-Top\n\n## §2.5.5 响应式断点\n| 断点名 | 范围 |\n|--------|------|\n| 手机 | < 768px |\n| 桌面 | ≥ 1024px |\n""")
        top_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write("""<!DOCTYPE html><html><head><style>
        @media (max-width: 768px) { .a { width:100%; } }
        </style></head><body></body></html>""")
        html_path = f.name
    try:
        result = run_audit(html_path, "ui", [top_path])
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "U-B5"]
        assert any("1024" in m for m in msgs), f"断点失败: {msgs}"
        assert not any("768" in m for m in msgs), f"不应报告存在的断点: {msgs}"
        print("✅ test_responsive_breakpoint")
    finally:
        os.unlink(top_path); os.unlink(html_path)

def test_reverse_feature_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| FP-001 | A |\n\n## §6 业务规则\n规则1：当 FP-002 触发时...\n\n## §7 错误处理\nERR-001：当 FP-003 触发时...\n""")
        path = f.name
    try:
        result = run_audit(path, "prd")
        msgs6 = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-A8"]
        msgs7 = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-A10"]
        assert any("FP-002" in m for m in msgs6), f"P-A8 失败: {msgs6}"
        assert any("FP-003" in m for m in msgs7), f"P-A10 失败: {msgs7}"
        print("✅ test_reverse_feature_ref")
    finally:
        os.unlink(path)

def test_interface_inventory_match():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §4 接口设计\n### 4.1 创建\n| URL | `POST /api/tickets` |\n| 功能 | 创建工单 |\n\n## §13 接口清单\n| 序号 | 接口名 | 方法 | 路径 |\n|------|--------|------|------|\n| 1 | 查询 | GET | /api/tickets |\n""")
        path = f.name
    try:
        result = run_audit(path, "tech")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "T-A9"]
        assert any("POST /api/tickets" in m for m in msgs), f"T-A9 正向失败: {msgs}"
        assert any("GET /api/tickets" in m for m in msgs), f"T-A9 反向失败: {msgs}"
        print("✅ test_interface_inventory_match")
    finally:
        os.unlink(path)

def test_page_structure():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# 交互设计-v1-首页\n\n# 首页\n## 页面结构\n## 组件交互\n## 状态机\n## 页面流程\n## 异常处理
## 与 PRD 对应\n\n# 列表页\n## 页面结构\n## 组件交互\n""")
        path = f.name
    try:
        result = run_audit(path, "interaction")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "I-A2"]
        assert any("列表页" in m and "状态机" in m for m in msgs), f"I-A2 失败: {msgs}"
        assert not any("首页" in m for m in msgs), f"不应报告完整页面: {msgs}"
        print("✅ test_page_structure")
    finally:
        os.unlink(path)

def test_table_field_interface_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §3 数据模型\n| 字段名 | 类型 |\n|--------|------|\n| user_id | BIGINT |\n| ticket_title | VARCHAR |\n\n## §4 接口设计\n| URL | `POST /api/tickets` |\n| 请求参数 | user_id |\n""")
        path = f.name
    try:
        result = run_audit(path, "tech")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "T-A10"]
        assert any("ticket_title" in m for m in msgs), f"T-A10 失败: {msgs}"
        assert not any("user_id" in m for m in msgs), f"不应报告存在的字段: {msgs}"
        print("✅ test_table_field_interface_ref")
    finally:
        os.unlink(path)

def test_exception_interface_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n## §4 接口设计\n错误码：ERR-TICKET-001\n\n## §7 异常处理\nERR-TICKET-001：网络错误\nERR-TICKET-002：权限不足\n""")
        path = f.name
    try:
        result = run_audit(path, "tech")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "T-A11"]
        assert any("ERR-TICKET-002" in m for m in msgs), f"T-A11 失败: {msgs}"
        assert not any("ERR-TICKET-001" in m for m in msgs), f"不应报告存在的错误码: {msgs}"
        print("✅ test_exception_interface_ref")
    finally:
        os.unlink(path)

def test_test_case_feature_ref():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test\n\n## §1 功能测试用例\n| 用例编号 | 用例名称 | 功能点 | 验收标准 |\n|---------|---------|--------|---------|\n| TC-001 | 登录 | FP-001 | AC-001 |\n| TC-002 | 注册 | — | — |\n""")
        path = f.name
    try:
        result = run_audit(path, "test")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "S-A3"]
        assert any("TC-002" in m and "功能点编号" in m for m in msgs), f"S-A3 功能点失败: {msgs}"
        assert any("TC-002" in m and "验收标准编号" in m for m in msgs), f"S-A3 验收标准失败: {msgs}"
        print("✅ test_test_case_feature_ref")
    finally:
        os.unlink(path)

def test_test_exception_coverage():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Test\n\n## §2 异常测试用例\n参数非法、权限不足、数据不存在\n""")
        path = f.name
    try:
        result = run_audit(path, "test")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "S-A4"]
        assert any("网络异常" in m for m in msgs), f"S-A4 失败: {msgs}"
        print("✅ test_test_exception_coverage")
    finally:
        os.unlink(path)

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
    print("\n🎉 All tests passed!")
