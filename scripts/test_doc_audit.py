#!/usr/bin/env python3
"""doc-audit.py 冒烟测试：验证新增规则的基本功能"""

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
    """T-B1: 双向映射规则"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-', delete=False) as f:
        f.write("""# PRD\n\n## §3 功能需求\n| 功能编号 | 名称 |\n|---------|------|\n| FP-001 | A |\n| FP-002 | B |\n""")
        prd_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tech\n\n**覆盖功能点**：FP-001, FP-003\n\n## §4 接口设计\n| 对应功能点 |\n|-----------|\n| FP-001 |\n""")
        tech_path = f.name
    try:
        result = run_audit(tech_path, "tech", [prd_path])
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "T-B1"]
        assert any("FP-002" in m and "无对应引用" in m for m in msgs), f"正向检查失败: {msgs}"
        assert any("FP-003" in m and "不存在" in m for m in msgs), f"反向检查失败: {msgs}"
        print("✅ test_bidirectional_mapping passed")
    finally:
        os.unlink(prd_path)
        os.unlink(tech_path)

def test_cross_doc_terminology():
    """P-B2: 跨产物术语一致性"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', prefix='prd-top-level-', delete=False) as f:
        f.write("""# PRD-顶层定义\n\n## §4 术语表\n| 术语 | 禁止别名 |\n|------|---------|\n| 工单 | 不可称"任务单" |\n""")
        top_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# PRD-模块\n\n## §3 功能需求\n用户创建任务单。\n""")
        mod_path = f.name
    try:
        result = run_audit(mod_path, "prd", [top_path])
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-B2"]
        assert any("任务单" in m for m in msgs), f"术语检查失败: {msgs}"
        print("✅ test_cross_doc_terminology passed")
    finally:
        os.unlink(top_path)
        os.unlink(mod_path)

def test_broken_internal_link():
    """P-A16: 内部链接完整性"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Doc\n\n## §1 A\n参见 §1。\n\n## §2 B\n参见 §5。\n""")
        path = f.name
    try:
        result = run_audit(path, "prd")
        msgs = [i["message"] for i in result["mechanical_issues"] if i["check_id"] == "P-A16"]
        assert any("§5" in m for m in msgs), f"断裂链接检查失败: {msgs}"
        assert not any("§3" in m for m in msgs), f"不应报告存在的链接: {msgs}"
        print("✅ test_broken_internal_link passed")
    finally:
        os.unlink(path)

def test_responsive_breakpoint():
    """U-B5: 响应式断点一致性"""
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
        assert any("1024" in m for m in msgs), f"断点检查失败: {msgs}"
        assert not any("768" in m for m in msgs), f"不应报告存在的断点: {msgs}"
        print("✅ test_responsive_breakpoint passed")
    finally:
        os.unlink(top_path)
        os.unlink(html_path)

if __name__ == "__main__":
    test_bidirectional_mapping()
    test_cross_doc_terminology()
    test_broken_internal_link()
    test_responsive_breakpoint()
    print("\n🎉 All tests passed!")
