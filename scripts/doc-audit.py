#!/usr/bin/env python3
"""
doc-audit.py — 文档一致性审计工具（标准库 only）

用法:
  # 全量审计
  python scripts/doc-audit.py <doc_path> --type prd --upstream upstream1.md upstream2.md

  # 增量审计（仅检查变更的功能点/页面/章节）
  python scripts/doc-audit.py <doc_path> --type prd --upstream up1.md --delta <标识符列表>

  # 扫描下游影响（输出受影响的下游文档清单）
  python scripts/doc-audit.py <doc_path> --type prd --scan-downstream ./docs/

输出: 结构化 JSON，包含 mechanical_issues / semantic_hints / summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Markdown AST（轻量、标准库 only）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MarkdownNode:
    type: str  # heading, table, paragraph, code, list, blockquote, raw
    content: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    children: List[MarkdownNode] = field(default_factory=list)


class MarkdownParser:
    """基于状态机的轻量 Markdown 解析器。支持 heading / table / code / list / paragraph。"""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.pos = 0
        self.nodes: List[MarkdownNode] = []

    def parse(self) -> List[MarkdownNode]:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()
            if not stripped:
                self.pos += 1
                continue
            if stripped.startswith("```"):
                self.nodes.append(self._parse_code_block())
            elif stripped.startswith("|"):
                self.nodes.append(self._parse_table())
            elif stripped.startswith("#"):
                self.nodes.append(self._parse_heading())
            elif re.match(r"^[-*+\d]+[.)]?\s", stripped):
                self.nodes.append(self._parse_list())
            elif stripped.startswith(">"):
                self.nodes.append(self._parse_blockquote())
            else:
                self.nodes.append(self._parse_paragraph())
        return self.nodes

    def _parse_heading(self) -> MarkdownNode:
        line = self.lines[self.pos].strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        level = len(m.group(1)) if m else 1
        text = m.group(2).strip() if m else line
        self.pos += 1
        return MarkdownNode(type="heading", content=text, meta={"level": level})

    def _parse_code_block(self) -> MarkdownNode:
        fence = self.lines[self.pos].strip()
        lang = fence[3:].strip() if len(fence) > 3 else ""
        self.pos += 1
        lines: List[str] = []
        while self.pos < len(self.lines):
            if self.lines[self.pos].strip().startswith("```"):
                self.pos += 1
                break
            lines.append(self.lines[self.pos])
            self.pos += 1
        return MarkdownNode(type="code", content="\n".join(lines), meta={"lang": lang})

    def _parse_table(self) -> MarkdownNode:
        rows: List[List[str]] = []
        while self.pos < len(self.lines):
            line = self.lines[self.pos].strip()
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line[1:].split("|")]
            # 去掉末尾空单元格（因行尾 | 产生）
            if cells and not cells[-1]:
                cells.pop()
            rows.append(cells)
            self.pos += 1
        return MarkdownNode(type="table", content="", meta={"rows": rows})

    def _parse_list(self) -> MarkdownNode:
        items: List[str] = []
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()
            if not stripped:
                self.pos += 1
                continue
            if not re.match(r"^[-*+\d]+[.)]?\s", stripped):
                break
            items.append(stripped)
            self.pos += 1
        return MarkdownNode(type="list", content="\n".join(items))

    def _parse_blockquote(self) -> MarkdownNode:
        lines: List[str] = []
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if not line.strip().startswith(">"):
                break
            lines.append(line.strip().lstrip(">").strip())
            self.pos += 1
        return MarkdownNode(type="blockquote", content="\n".join(lines))

    def _parse_paragraph(self) -> MarkdownNode:
        lines: List[str] = []
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.strip()
            if not stripped:
                self.pos += 1
                break
            if stripped.startswith(("#", "|", "```", ">")) or re.match(r"^[-*+\d]+[.)]?\s", stripped):
                break
            lines.append(line)
            self.pos += 1
        return MarkdownNode(type="paragraph", content="\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 通用审计基类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditIssue:
    type: str
    severity: str  # blocking / warning
    location: str
    message: str


@dataclass
class AuditHint:
    type: str
    severity: str  # warning / info
    location: str
    message: str


class DocumentAuditor:
    """审计器基类。子类覆盖 run() 调用通用检查 + 专用检查。"""

    def __init__(
        self,
        doc_path: str,
        upstream_paths: Optional[List[str]] = None,
        delta_scope: Optional[List[str]] = None,
    ):
        self.doc_path = Path(doc_path)
        self.upstream_paths = [Path(p) for p in (upstream_paths or [])]
        self.delta_scope = set(delta_scope or [])  # 增量范围，如 {"USER-001", "PAGE-001"}（示例，实际标识符格式以项目定义为准）
        self.raw_text = self.doc_path.read_text(encoding="utf-8")
        self.nodes = MarkdownParser(self.raw_text).parse()
        self.issues: List[AuditIssue] = []
        self.hints: List[AuditHint] = []
        self.upstream_texts: Dict[str, str] = {}
        for p in self.upstream_paths:
            if p.exists():
                self.upstream_texts[p.name] = p.read_text(encoding="utf-8")

    # ── 输出 ──
    def add_issue(self, check_type: str, severity: str, location: str, message: str):
        self.issues.append(AuditIssue(check_type, severity, location, message))

    def add_hint(self, check_type: str, severity: str, location: str, message: str):
        self.hints.append(AuditHint(check_type, severity, location, message))

    def report(self) -> dict:
        blocking = [i for i in self.issues if i.severity == "blocking"]
        return {
            "passed": len(blocking) == 0,
            "doc": str(self.doc_path),
            "delta_scope": sorted(self.delta_scope) if self.delta_scope else None,
            "mechanical_issues": [i.__dict__ for i in self.issues],
            "semantic_hints": [h.__dict__ for h in self.hints],
            "summary": {
                "blocking": len(blocking),
                "warning": len([i for i in self.issues if i.severity == "warning"]),
                "hints": len(self.hints),
            },
        }

    # ── 通用工具 ──
    def _find_sections(self) -> List[Tuple[int, str]]:
        """返回所有 heading 节点: [(level, text), ...]"""
        return [
            (n.meta.get("level", 1), n.content)
            for n in self.nodes
            if n.type == "heading"
        ]

    def _section_text(self, header_pattern: str) -> str:
        """提取匹配 header_pattern 的章节及其子章节文本（直到同级或更高级 heading）。"""
        start = -1
        level = 6
        for idx, n in enumerate(self.nodes):
            if n.type == "heading" and re.search(header_pattern, n.content):
                start = idx
                level = n.meta.get("level", 1)
                break
        if start == -1:
            return ""
        parts: List[str] = []
        for n in self.nodes[start + 1 :]:
            if n.type == "heading" and n.meta.get("level", 1) <= level:
                break
            if n.type == "table":
                rows = n.meta.get("rows", [])
                for row in rows:
                    parts.append("| " + " | ".join(row) + " |")
            else:
                parts.append(n.content)
        return "\n".join(parts)

    def _extract_table_after(self, header_pattern: str) -> Optional[List[List[str]]]:
        """在匹配 header_pattern 的 heading/paragraph 后找到第一个 table 节点。"""
        found = False
        for n in self.nodes:
            if n.type in ("heading", "paragraph") and re.search(header_pattern, n.content):
                found = True
                continue
            if found and n.type == "table":
                return n.meta.get("rows", [])
            if found and n.type == "heading":
                # 如果 heading 级别高于触发 heading 则停止，但 upstream 表格通常在 paragraph 后面
                # 这里放宽：遇到任何 heading 不立即停止，只有当 heading 级别 <=2 且不是我们要找的才停止
                if n.meta.get("level", 1) <= 2:
                    break
        return None

    def _collect_numbers(self, prefix: str, text: str) -> List[int]:
        pattern = rf"{prefix}(\d+)"
        return sorted({int(m) for m in re.findall(pattern, text)})

    # ── 通用机械检查 ──
    def check_number_continuity(self, prefix: str, location: str, text: str | None = None):
        text = self.filter_delta_text(text or self.raw_text)
        if not text.strip():
            return
        numbers = self._collect_numbers(prefix, text)
        if not numbers:
            return
        for i in range(len(numbers) - 1):
            gap = numbers[i + 1] - numbers[i]
            if gap > 1:
                # 检查是否有预留声明（如"F107、F108 为预留跳号"）
                skipped = [f"{prefix}{n:03d}" for n in range(numbers[i] + 1, numbers[i + 1])]
                has_reserved = any(
                    re.search(rf"{s}.*预留|预留.*{s}|编号段.*{s}|{s}.*编号段", self.raw_text)
                    for s in skipped
                )
                if has_reserved:
                    continue
                self.add_issue(
                    "number_gap",
                    "blocking",
                    location,
                    f"{prefix} 编号不连续，缺少 {prefix}{numbers[i]+1:03d}"
                    f"（已有 {prefix}{numbers[i]:03d}, {prefix}{numbers[i+1]:03d}）",
                )

    def check_duplicate_numbers(self, prefix: str, location: str, text: str | None = None):
        text = self.filter_delta_text(text or self.raw_text)
        if not text.strip():
            return
        pattern = rf"{prefix}(\d+)"
        numbers = re.findall(pattern, text)
        seen: Set[str] = set()
        for n in numbers:
            if n in seen:
                self.add_issue(
                    "duplicate_number",
                    "blocking",
                    location,
                    f"{prefix}{n} 出现重复",
                )
            seen.add(n)

    def check_required_sections(self, required_headers: List[str]):
        headings = [n.content for n in self.nodes if n.type == "heading"]
        for header in required_headers:
            if not any(header in h for h in headings):
                self.add_issue(
                    "missing_section",
                    "blocking",
                    "章节结构",
                    f"缺少必填章节: {header}",
                )

    def check_table_format(self):
        for idx, n in enumerate(self.nodes, 1):
            if n.type != "table":
                continue
            rows = n.meta.get("rows", [])
            if not rows:
                continue
            if len(rows) < 2:
                self.add_issue(
                    "table_format",
                    "warning",
                    f"表格 #{idx}",
                    "表格少于两行，可能格式错误",
                )
                continue
            # 检查分隔行（Markdown 表格第二行应为 |---|---|）
            sep = rows[1]
            if not all(re.match(r"^:?-+:?$", cell) for cell in sep if cell.strip()):
                self.add_issue(
                    "table_format",
                    "warning",
                    f"表格 #{idx}",
                    "第二行分隔线格式不正确",
                )
            # 检查列数一致
            col_counts = [len(r) for r in rows]
            if len(set(col_counts)) > 1:
                self.add_issue(
                    "table_format",
                    "blocking",
                    f"表格 #{idx}",
                    f"列数不一致: {col_counts}",
                )

    def check_upstream_references(self):
        """检查 upstream-document 表格是否存在，且引用的文档路径可解析。"""
        # 提取文件头部：从开头到第一个 ## 级 heading（不含 upstream 自身所在区域）
        header_text = ""
        in_header = True
        upstream_found = False
        for n in self.nodes:
            if n.type == "heading" and n.meta.get("level", 1) <= 2:
                if upstream_found:
                    break
                in_header = False
            if "上游文档" in n.content:
                in_header = True
                upstream_found = True
            if in_header:
                header_text += n.content + "\n"
        if not upstream_found:
            self.add_issue(
                "missing_upstream",
                "blocking",
                "文件头部",
                "缺少 upstream-document 声明",
            )
            return
        # 提取表格中的文档名
        table = self._extract_table_after(r"上游文档")
        if not table or len(table) < 2:
            self.add_issue(
                "missing_upstream",
                "blocking",
                "文件头部",
                "upstream-document 表格格式错误或为空",
            )
            return
        for row in table[1:]:  # 跳过表头
            if len(row) < 1:
                continue
            doc_name = row[0].strip()
            # 跳过 Markdown 表格分隔行（如 ------）
            if re.match(r"^:?-+:?$", doc_name):
                continue
            # 简单启发式：如果看起来像文件名，检查同目录或给定 upstream_paths 中是否存在
            possible_names = [doc_name, doc_name + ".md"]
            found = any(
                (self.doc_path.parent / name).exists() or name in [p.name for p in self.upstream_paths]
                for name in possible_names
            )
            if not found and "/" in doc_name:
                found = (self.doc_path.parent / doc_name).exists() or (self.doc_path.parent / (doc_name + ".md")).exists()
            if not found and "规范" not in doc_name and "AGENTS" not in doc_name:
                # 放宽：顶层定义或 AGENTS 可能尚未落地为文件
                self.add_hint(
                    "upstream_not_found",
                    "warning",
                    "文件头部",
                    f"上游文档 '{doc_name}' 在当前目录或 --upstream 参数中未找到，请确认路径",
                )

    def check_error_code_format(self, text: str | None = None, error_prefixes: Optional[List[str]] = None):
        """检查错误码格式是否符合项目 PRD-顶层定义声明的格式。
        如未提供 error_prefixes，跳过格式检查（格式完全由项目自定义）。
        """
        text = self.filter_delta_text(text or self.raw_text)
        if not text.strip() or not error_prefixes:
            return
        for prefix in error_prefixes:
            codes = re.findall(rf"`?({prefix}\w+)`?", text)
            for code in codes:
                self.add_hint(
                    "error_code_found",
                    "info",
                    "错误码",
                    f"发现错误码 {code}，请确认格式符合项目 PRD-顶层定义",
                )

    def check_term_consistency(self, term_list: Optional[List[str]] = None):
        """术语一致性检查。
        如果提供 term_list，则检查文档中是否出现 term_list 中的术语变形；
        否则从加粗文本中提取候选术语，并检测常见混用。
        """
        filtered_text = self.filter_delta_text(self.raw_text)
        if not filtered_text.strip():
            return
        # 提取加粗术语
        bold_terms = re.findall(r"\*\*([^*]+?)\*\*", filtered_text)
        term_counts: Dict[str, int] = {}
        for t in bold_terms:
            t = t.strip()
            if 2 <= len(t) <= 20:
                term_counts[t] = term_counts.get(t, 0) + 1

        # 项目自定义术语冲突（从 upstream PRD-顶层定义中提取术语表）
        if term_list:
            found_terms = {t for t in term_counts}
            for term in term_list:
                variants = [term, term.replace("用户", "客户"), term.replace("订单", "单据")]
                matches = [v for v in variants if v in found_terms]
                if len(matches) > 1:
                    self.add_hint(
                        "term_inconsistency",
                        "warning",
                        "术语一致性",
                        f"文档中同时出现 {' / '.join(matches)}，请确认是否为同一概念",
                    )
        else:
            # 默认常见混用检测（在过滤后的文本中进行）
            common_confusions = [
                ("用户", "客户"),
                ("订单", "单据"),
                ("商品", "产品"),
                ("金额", "价格"),
            ]
            found_terms = set(term_counts.keys())
            for a, b in common_confusions:
                if a in found_terms and b in found_terms:
                    self.add_hint(
                        "term_inconsistency",
                        "warning",
                        "术语一致性",
                        f"文档中同时出现 '{a}' 和 '{b}'，请确认是否为同一概念",
                    )

    # ── 增量审计工具 ──
    def filter_delta_text(self, text: str) -> str:
        """如果设置了 delta_scope，按块保留包含这些标识符的内容。

        分块策略：按空行分块，块内包含任何 delta 标识符则保留整个块。
        这样既能聚焦变更范围，又不会破坏表格/列表的上下文结构，
        避免编号连续性等检查因上下文缺失而误报。
        """
        if not self.delta_scope:
            return text
        lines = text.splitlines()
        # 按空行分块
        blocks: List[List[str]] = []
        current_block: List[str] = []
        for line in lines:
            if line.strip() == "":
                if current_block:
                    blocks.append(current_block)
                    current_block = []
            else:
                current_block.append(line)
        if current_block:
            blocks.append(current_block)

        result: List[str] = []
        for block in blocks:
            block_text = "\n".join(block)
            if any(scope in block_text for scope in self.delta_scope):
                result.extend(block)
        return "\n".join(result)

    def run(self):
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 按文档类型的专用审计器
# ═══════════════════════════════════════════════════════════════════════════════

class PRDAuditor(DocumentAuditor):
    """PRD 文档审计器"""

    def run(self):
        # 结构一致性
        self.check_required_sections([
            "背景与目标", "用户与场景", "功能需求",
            "非功能需求", "数据模型", "业务规则", "错误处理", "验收标准", "依赖与范围",
        ])

        # 提取 §3 功能需求文本（用于后续引用检查）
        sec3_text = self._section_text(r"§3\s+功能需求")
        sec5_text = self._section_text(r"§5\s+数据模型")
        sec6_text = self._section_text(r"§6\s+业务规则")
        sec7_text = self._section_text(r"§7\s+错误处理")
        sec8_text = self._section_text(r"§8\s+验收标准")

        # 编号连续性 & 重复（只在分配表格中检查，避免后续章节引用导致误报）
        # 提取 §3 表格第一列（跳过表头和分隔行）
        sec3_table = self._extract_table_after(r"§3\s+功能需求")
        sec3_first_col = "\n".join(
            row[0] for row in (sec3_table or [])
            if row and not re.match(r"^:?-+:?$", row[0])
        )

        self.check_number_continuity("F", "§3 功能需求", sec3_first_col)
        self.check_duplicate_numbers("F", "§3 功能需求", sec3_first_col)

        # 表格格式
        self.check_table_format()

        # 术语一致性
        self.check_term_consistency()

        # upstream
        self.check_upstream_references()

        # 内部自洽性：§3 的功能标识在 §5/§6/§7/§8 中至少引用一次
        downstream_text = sec5_text + sec6_text + sec7_text + sec8_text
        if sec3_first_col.strip():
            # 从功能需求第一列提取所有标识符（不假设格式）
            feature_ids = [line.strip() for line in sec3_first_col.splitlines() if line.strip() and not re.match(r"^:?-+:?$", line.strip())]
            for fid in feature_ids:
                if fid not in downstream_text:
                    self.add_hint(
                        "unreferenced_feature",
                        "warning",
                        "内部自洽性",
                        f"功能点 {fid} 在 §5/§6/§7/§8 中未被引用，请确认是否有遗漏章节",
                    )

        # §7 每个错误码在 §6 中有对应触发场景
        # 从 sec7 中提取反引号包裹的标识符作为候选错误码
        err_codes = re.findall(r"`([^`\s]+)`", sec7_text)
        for code in set(err_codes):
            if code not in sec6_text:
                self.add_hint(
                    "error_code_no_rule",
                    "warning",
                    "内部自洽性",
                    f"错误码 {code} 在 §6 业务规则中无对应触发场景",
                )

        # §8 每条验收标准对应 §3 的一个功能点
        ac_items = re.findall(r"§8\.(\d+)", sec8_text)
        for num in ac_items:
            # 提取对应行，检查是否包含 §3 中的任意功能标识
            has_ref = any(fid in sec8_text for fid in feature_ids) if feature_ids else False
            if not has_ref and feature_ids:
                self.add_issue(
                    "acceptance_no_feature",
                    "blocking",
                    "§8 验收标准",
                    f"验收项 §8.{num} 未关联任何功能点",
                )


class InteractionAuditor(DocumentAuditor):
    """交互设计文档审计器"""

    def run(self):
        # 文档级检查
        self.check_required_sections([
            "设计系统引用", "页面结构", "组件交互", "状态机", "页面流程", "异常处理", "与 PRD 对应",
        ])

        # 检查文档级"设计系统引用"
        doc_text = "\n".join([n.content for n in self.nodes])
        if "设计系统引用" not in doc_text:
            self.add_issue(
                "missing_design_system_reference",
                "blocking",
                "交互设计文档",
                "缺少文档级章节: 设计系统引用",
            )

        # 提取所有页面章节文本（一级标题匹配页面编号格式）
        page_sections: List[str] = []
        current_section = ""
        page_titles: List[str] = []
        for n in self.nodes:
            if n.type == "heading" and re.search(r"§\d+\s+P\d+", n.content):
                if current_section:
                    page_sections.append(current_section)
                current_section = n.content + "\n"
                page_titles.append(n.content)
            elif current_section:
                current_section += n.content + "\n"
        if current_section:
            page_sections.append(current_section)

        # 每个页面检查 6 个必含子节
        for sec in page_sections:
            for sub in ["页面结构", "组件交互", "状态机", "页面流程", "异常处理", "与 PRD 对应"]:
                if sub not in sec:
                    # 提取页面编号用于定位
                    pm = re.search(r"(P\d+)", sec)
                    page_id = pm.group(1) if pm else "未知页面"
                    self.add_issue(
                        "missing_subsection",
                        "blocking",
                        f"{page_id} 交互设计",
                        f"页面 {page_id} 缺少子节: {sub}",
                    )

        # 只在页面标题中检查编号重复/连续，避免"与 PRD 对应"子节中的引用导致误报
        title_text = "\n".join(page_titles)
        self.check_number_continuity("P", "页面编号", title_text)
        self.check_duplicate_numbers("P", "页面编号", title_text)
        self.check_table_format()
        self.check_term_consistency()
        self.check_upstream_references()


class TechAuditor(DocumentAuditor):
    """技术方案文档审计器"""

    def run(self):
        self.check_required_sections([
            "关联文档", "服务概述", "技术实现要点",
            "数据模型", "接口设计", "接口清单",
        ])

        sec5_text = self._section_text(r"§5\s+数据模型")
        sec6_text = self._section_text(r"§6\s+接口设计")
        sec8_text = self._section_text(r"§8\s+异常处理")
        sec10_text = self._section_text(r"§10\s+接口清单")

        self.check_table_format()
        self.check_term_consistency()
        self.check_upstream_references()
        self.check_interface_consistency(sec6_text, sec10_text)
        self.check_error_code_format()

        # §8 每个异常场景对应 PRD §7 的一个错误码或模块特定异常
        ex_codes = re.findall(r"`([^`\s]+)`", sec8_text)
        for code in set(ex_codes):
            # 检查是否也在 §6 接口设计中出现
            if code not in sec6_text:
                self.add_hint(
                    "exception_not_in_api",
                    "warning",
                    "§8 异常处理",
                    f"异常 {code} 在 §6 接口设计中未作为错误码返回",
                )

    def check_interface_consistency(self, sec6_text: str, sec10_text: str):
        """检查 §6 接口设计与 §10 接口清单是否一一对应"""
        # §6 中接口通常在反引号内，如 `POST /api/v1/orders`
        pattern_6 = r"`(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}-]+)`"
        paths_6 = set(re.findall(pattern_6, sec6_text))

        # §10 中接口在表格单元格内，格式如 `| 提交订单 | POST | /api/v1/orders | ... |`
        # 需要匹配方法列和路径列（中间有 | 分隔）
        pattern_10 = r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*(/[\w/{}-]+)\s*\|"
        paths_10 = set(re.findall(pattern_10, sec10_text))

        missing_in_10 = paths_6 - paths_10
        missing_in_6 = paths_10 - paths_6
        for method, path in missing_in_10:
            self.add_issue(
                "interface_mismatch",
                "blocking",
                "§10 接口清单",
                f"§6 中存在接口 {method} {path}，但 §10 接口清单中缺失",
            )
        for method, path in missing_in_6:
            self.add_issue(
                "interface_mismatch",
                "blocking",
                "§6 接口设计",
                f"§10 接口清单中存在 {method} {path}，但 §6 中无详细定义",
            )


class UIAuditor(DocumentAuditor):
    """UI 设计文档审计器"""

    def run(self):
        self.check_required_sections([
            "顶层定义引用", "组件规范", "页面设计",
        ])

        # 只从 §4 页面设计的子章节标题中提取页面编号，避免正文中引用导致误报
        page_headings = []
        in_sec4 = False
        for n in self.nodes:
            if n.type == "heading" and re.search(r"§4\s+页面设计", n.content):
                in_sec4 = True
                continue
            if in_sec4 and n.type == "heading":
                if n.meta.get("level", 1) <= 2:
                    break
                page_headings.append(n.content)
        title_text = "\n".join(page_headings)

        self.check_number_continuity("P", "页面编号", title_text)
        self.check_duplicate_numbers("P", "页面编号", title_text)
        self.check_table_format()
        self.check_term_consistency()
        self.check_upstream_references()

        # §4 每个页面必须有默认/空/错误三种状态
        sec4_text = self._section_text(r"§4\s+页面设计")
        page_blocks = re.split(r"\n#{2,4}\s+", sec4_text)
        for block in page_blocks:
            if not block.strip():
                continue
            states = ["默认状态", "空状态", "错误状态"]
            missing = [s for s in states if s not in block]
            if missing:
                pm = re.search(r"(P\d+)", block)
                page_id = pm.group(1) if pm else "未知页面"
                self.add_issue(
                    "missing_ui_state",
                    "blocking",
                    f"§4 {page_id}",
                    f"页面 {page_id} 缺少状态描述: {', '.join(missing)}",
                )


class TestAuditor(DocumentAuditor):
    """测试报告审计器"""

    def run(self):
        self.check_required_sections([
            "功能测试用例", "异常测试用例", "覆盖检查报告",
        ])

        sec1_text = self._section_text(r"§1\s+功能测试用例")
        sec2_text = self._section_text(r"§2\s+异常测试用例")

        # 测试用例编号格式完全由项目自定义，此处不做硬编码格式检查
        # 如需检查连续性，可通过 --delta 参数指定具体测试用例范围
        self.check_table_format()
        self.check_term_consistency()
        self.check_upstream_references()

        # §3 覆盖检查报告中每个验收标准在 §1/§2 中有对应用例
        sec3_text = self._section_text(r"§3\s+覆盖检查报告")
        all_cases = sec1_text + sec2_text
        ac_refs = re.findall(r"§8\.(\d+)", sec3_text)
        for ref in set(ac_refs):
            if f"§8.{ref}" not in all_cases:
                self.add_issue(
                    "uncovered_acceptance",
                    "blocking",
                    "§3 覆盖检查报告",
                    f"验收标准 §8.{ref} 在 §1/§2 中无对应测试用例",
                )

    def check_number_continuity(self, prefix: str, location: str, text: str | None = None):
        """测试用例编号连续性检查（支持任意位数）"""
        text = text or self.raw_text
        # 提取 prefix + 任意位数字
        numbers = sorted({int(m) for m in re.findall(rf"{prefix}(\d+)", text)})
        if not numbers:
            return
        for i in range(len(numbers) - 1):
            if numbers[i + 1] - numbers[i] > 1:
                self.add_issue(
                    "number_gap",
                    "blocking",
                    location,
                    f"{prefix} 编号不连续，缺少 {prefix}{numbers[i]+1}"
                    f"（已有 {prefix}{numbers[i]}, {prefix}{numbers[i+1]}）",
                )

    def check_duplicate_numbers(self, prefix: str, location: str, text: str | None = None):
        """测试用例编号重复检查（支持任意位数）"""
        text = text or self.raw_text
        numbers = re.findall(rf"{prefix}(\d+)", text)
        seen: set[str] = set()
        for n in numbers:
            if n in seen:
                self.add_issue(
                    "duplicate_number",
                    "blocking",
                    location,
                    f"{prefix}{n} 出现重复",
                )
            seen.add(n)


class GlobalPRDAuditor(DocumentAuditor):
    """PRD 顶层定义审计器"""

    def run(self):
        self.check_required_sections([
            "产品概述", "功能范围", "版本里程碑",
            "术语表", "状态值", "错误码规则",
        ])
        self.check_table_format()
        self.check_error_code_format()

        # 检查是否出现"后续版本"等延迟占位（里程碑表除外）
        body = self.raw_text
        # 去掉 §3 版本里程碑章节
        milestone_start = body.find("§3")
        milestone_end = body.find("§4")
        if milestone_start != -1 and milestone_end != -1:
            body = body[:milestone_start] + body[milestone_end:]
        prohibited = ["后续版本", "v1.x+", "后续迭代", "后续补充"]
        for word in prohibited:
            if word in body:
                self.add_issue(
                    "placeholder_detected",
                    "blocking",
                    "顶层定义",
                    f"正文出现延迟实现占位词: '{word}'（里程碑表除外）",
                )


class GlobalTechAuditor(DocumentAuditor):
    """技术顶层定义审计器"""

    def run(self):
        self.check_required_sections([
            "技术栈", "工程结构", "公共模块",
            "公共表定义", "全局接口约定", "全局安全规范",
        ])
        self.check_table_format()

        # 检查 2.5.2 响应结构包含 code/message/data
        sec25_text = self._section_text(r"2\.5\.2")
        if "code" not in sec25_text or "message" not in sec25_text or "data" not in sec25_text:
            self.add_issue(
                "response_structure",
                "blocking",
                "§2.5.2 统一响应结构",
                "未明确声明响应结构包含 code/message/data 三个字段",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 下游影响扫描器
# ═══════════════════════════════════════════════════════════════════════════════

def scan_downstream(doc_path: Path, docs_dir: Path) -> List[dict]:
    """扫描 docs_dir 下所有 Markdown 文件，找出引用了 doc_path 的下游文档。"""
    downstream: List[dict] = []
    target_name = doc_path.stem
    for md_file in docs_dir.rglob("*.md"):
        if md_file.resolve() == doc_path.resolve():
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        # 检查 upstream-document 表格中是否出现 target_name
        if target_name in text and "上游文档" in text:
            # 提取引用范围（粗略）
            scope_match = re.search(
                rf"\|\s*{re.escape(target_name)}\s*\|\s*[^|]+\|\s*([^|\n]+)\|",
                text,
            )
            scope = scope_match.group(1).strip() if scope_match else "未知"
            downstream.append({
                "path": str(md_file.relative_to(docs_dir)),
                "scope": scope,
            })
    return downstream


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 入口
# ═══════════════════════════════════════════════════════════════════════════════

AUDITOR_MAP = {
    "prd": PRDAuditor,
    "interaction": InteractionAuditor,
    "ui": UIAuditor,
    "tech": TechAuditor,
    "test": TestAuditor,
    "global-prd": GlobalPRDAuditor,
    "global-tech": GlobalTechAuditor,
}


def main():
    parser = argparse.ArgumentParser(description="文档一致性审计工具")
    parser.add_argument("doc_path", help="待审计文档路径")
    parser.add_argument(
        "--type",
        required=True,
        choices=list(AUDITOR_MAP.keys()),
        help="文档类型",
    )
    parser.add_argument(
        "--upstream",
        nargs="*",
        default=[],
        help="上游文档路径（可多个）",
    )
    parser.add_argument(
        "--delta",
        default="",
        help="增量审计范围，逗号分隔（标识符格式以项目 PRD-顶层定义为准）",
    )
    parser.add_argument(
        "--scan-downstream",
        metavar="DIR",
        default="",
        help="扫描指定目录下的下游引用，输出受影响文档清单",
    )
    parser.add_argument(
        "--terms",
        nargs="*",
        default=[],
        help="项目术语表（用于术语一致性检查）",
    )
    args = parser.parse_args()

    doc_path = Path(args.doc_path)
    if not doc_path.exists():
        print(json.dumps({"error": f"文件不存在: {doc_path}"}, ensure_ascii=False))
        sys.exit(1)

    # 下游扫描模式
    if args.scan_downstream:
        docs_dir = Path(args.scan_downstream)
        if not docs_dir.is_dir():
            print(json.dumps({"error": f"目录不存在: {docs_dir}"}, ensure_ascii=False))
            sys.exit(1)
        downstream = scan_downstream(doc_path, docs_dir)
        print(
            json.dumps(
                {
                    "mode": "downstream_scan",
                    "doc": str(doc_path),
                    "downstream_count": len(downstream),
                    "downstream": downstream,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(0)

    # 审计模式
    delta_scope = [s.strip() for s in args.delta.split(",") if s.strip()]
    auditor_cls = AUDITOR_MAP[args.type]
    auditor = auditor_cls(
        doc_path=str(doc_path),
        upstream_paths=args.upstream,
        delta_scope=delta_scope,
    )
    # 执行审计
    auditor.run()
    # 如提供了术语表，追加术语一致性检查
    if args.terms:
        auditor.check_term_consistency(args.terms)
    print(json.dumps(auditor.report(), ensure_ascii=False, indent=2))
    sys.exit(0 if auditor.report()["passed"] else 1)


if __name__ == "__main__":
    main()
