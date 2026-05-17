#!/usr/bin/env python3
"""
doc-audit.py — 文档一致性审计工具（标准库 only）

用法:
  # 全量审计
  python3 scripts/doc-audit.py <doc_path> --type prd --upstream upstream1.md upstream2.md

  # 增量审计（仅检查变更的功能点/页面/章节）
  python3 scripts/doc-audit.py <doc_path> --type prd --upstream up1.md --delta <标识符列表>

  # 扫描下游影响（输出受影响的下游文档清单）
  python3 scripts/doc-audit.py <doc_path> --type prd --scan-downstream ./docs/

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
        # upstream_paths 用于存在性校验，文本内容暂未使用

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
        """检查 upstream-document 表格是否存在，且引用的文档路径可解析。
        
        豁免：若 upstream-document 区域包含"示例""常见依赖""不要机械套用"等字样，
        视为 Skill 模板/写作指南，跳过 upstream 检查。
        """
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
        
        # 豁免：Skill 模板/写作指南中的 upstream-document 仅为示例
        if "不要机械套用" in header_text:
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
                (self.doc_path.parent / name).exists()
                or any(name == p.name and p.exists() for p in self.upstream_paths)
                for name in possible_names
            )
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
            "非功能需求", "数据模型", "业务规则", "错误处理", "验收标准", "依赖与范围", "附件",
        ])

        # 提取 §3 功能需求文本（用于后续引用检查）
        sec3_text = self._section_text(r"§3\s+功能需求")
        # sec5 数据模型通常不包含功能编号引用，已排除在 downstream_text 外
        sec6_text = self._section_text(r"§6\s+业务规则")
        sec7_text = self._section_text(r"§7\s+错误处理")
        sec8_text = self._section_text(r"§8\s+验收标准")

        # 编号连续性 & 重复（只在分配表格中检查，避免后续章节引用导致误报）
        # 提取 §3 表格第一列（跳过表头、分隔行和已知表头文本）
        sec3_table = self._extract_table_after(r"§3\s+功能需求")
        sec3_first_col = "\n".join(
            row[0] for row in (sec3_table or [])
            if row and not re.match(r"^:?-+:?$", row[0])
            and row[0].strip() not in ("功能编号", "编号", "ID")
        )

        # 功能编号前缀由项目 PRD-顶层定义编码规则决定，不做硬编码连续性检查

        # 表格格式
        self.check_table_format()

        # 术语一致性
        self.check_term_consistency()

        # upstream
        self.check_upstream_references()

        # 内部自洽性：§3 的功能标识在 §6/§7/§8 中至少引用一次
        # 注意：§5 数据模型通常不包含功能编号引用，纳入会产生噪音
        downstream_text = sec6_text + sec7_text + sec8_text
        if sec3_first_col.strip():
            # 从功能需求第一列提取所有标识符（不假设格式）
            feature_ids = [line.strip() for line in sec3_first_col.splitlines() if line.strip() and not re.match(r"^:?-+:?$", line.strip())]
            for fid in feature_ids:
                if fid not in downstream_text:
                    self.add_hint(
                        "unreferenced_feature",
                        "warning",
                        "内部自洽性",
                        f"功能点 {fid} 在 §6/§7/§8 中未被引用，请确认是否有遗漏章节",
                    )

        # §7 每个错误码在 §6 中有对应触发场景
        # 从 sec7 中提取反引号包裹的候选错误码，过滤掉字段名、状态值等非错误码内容
        err_codes = re.findall(rf"`({ERROR_CODE_RE})`", sec7_text)
        for code in set(err_codes):
            if code not in sec6_text:
                self.add_hint(
                    "error_code_no_rule",
                    "warning",
                    "内部自洽性",
                    f"错误码 {code} 在 §6 业务规则中无对应触发场景",
                )

        # §8 每条验收标准对应 §3 的一个功能点
        # 验收标准编号格式由项目自定义（如 ACC-001），从表格第一列提取
        sec8_table = self._extract_table_after(r"§8\s+验收标准")
        ac_rows = []
        if sec8_table:
            for row in sec8_table:
                if row and not re.match(r"^:?-+:?$", row[0]) \
                        and row[0].strip() not in ("验收项编号", "验收标准编号", "编号", "ID"):
                    ac_rows.append(row)
        for row in ac_rows:
            ac_id = row[0].strip()
            # 优先检查功能编号列（第二列），如存在则精确匹配
            feature_col = row[1].strip() if len(row) > 1 else ""
            has_ref = False
            if feature_col and feature_ids:
                # 按常见分隔符拆分后精确匹配，避免前缀误匹配（如 USER-001 误命中 USER-0010）
                col_parts = re.split(r"[,，;；\s|]+", feature_col)
                has_ref = any(fid == part for part in col_parts for fid in feature_ids)
            if not has_ref and feature_ids:
                # 回退：检查整行文本中是否出现功能点编号（使用词边界）
                ac_desc = " | ".join(row[1:]) if len(row) > 1 else ""
                has_ref = any(re.search(rf"\b{re.escape(fid)}\b", ac_desc) for fid in feature_ids)
            if not has_ref and feature_ids:
                self.add_issue(
                    "acceptance_no_feature",
                    "blocking",
                    "§8 验收标准",
                    f"验收项 {ac_id} 未关联任何功能点",
                )


class InteractionAuditor(DocumentAuditor):
    """交互设计文档审计器"""

    def run(self):
        # 文档级检查
        self.check_required_sections([
            "设计系统引用", "页面结构", "组件交互", "状态机", "页面流程", "异常处理", "与 PRD 对应",
        ])

        # 提取所有页面章节文本（一级标题匹配页面编号格式）
        # 页面编号格式由项目编码规则决定，支持任意前缀（如 PAGE-TICKET-001）
        page_sections: List[str] = []
        current_section = ""
        for n in self.nodes:
            # 匹配 §数字 后面跟着页面编号（支持任意前缀+数字格式）
            if n.type == "heading" and re.search(r"§\d+\s+[A-Z]+-[A-Z]+-\d+", n.content):
                if current_section:
                    page_sections.append(current_section)
                current_section = n.content + "\n"
            elif current_section:
                current_section += n.content + "\n"
        if current_section:
            page_sections.append(current_section)

        if not page_sections and self.nodes:
            # 豁免：Skill 模板/写作指南不包含真实页面章节
            if "不要机械套用" not in self.raw_text:
                self.add_issue(
                    "missing_page_sections",
                    "blocking",
                    "交互设计文档",
                    "未检测到任何符合格式的页面章节（如 §1 PAGE-TICKET-001），请确认页面编号格式",
                )

        # 每个页面检查 6 个必含子节
        for sec in page_sections:
            for sub in ["页面结构", "组件交互", "状态机", "页面流程", "异常处理", "与 PRD 对应"]:
                if sub not in sec:
                    # 提取页面编号用于定位
                    pm = re.search(r"([A-Z]+-[A-Z]+-\d+)", sec)
                    page_id = pm.group(1) if pm else "未知页面"
                    self.add_issue(
                        "missing_subsection",
                        "blocking",
                        f"{page_id} 交互设计",
                        f"页面 {page_id} 缺少子节: {sub}",
                    )

        # 页面编号格式由项目自定义，不硬编码连续性检查
        self.check_table_format()
        self.check_upstream_references()


class TechAuditor(DocumentAuditor):
    """技术方案文档审计器"""

    def run(self):
        self.check_required_sections([
            "技术决策", "依赖关系", "数据模型", "接口设计",
            "状态机设计", "核心流程", "异常处理", "性能与扩展性",
            "高可用设计", "安全设计", "监控与日志", "灰度与回滚",
            "接口清单", "风险评估",
        ])

        sec3_text = self._section_text(r"§3\s+数据模型")
        sec4_text = self._section_text(r"§4\s+接口设计")
        sec7_text = self._section_text(r"§7\s+异常处理")
        sec13_text = self._section_text(r"§13\s+接口清单")

        self.check_table_format()
        self.check_upstream_references()
        self.check_interface_consistency(sec4_text, sec13_text)
        # check_error_code_format 需要传入 error_prefixes 参数，当前无项目级配置，暂不调用
        # self.check_error_code_format(error_prefixes=[...])

        # §7 每个异常场景对应 PRD 错误处理或模块特定异常
        # 提取符合错误码格式的反引号内容（如 ERR-001、TICKET-001）
        ex_codes = re.findall(rf"`({ERROR_CODE_RE})`", sec7_text)
        for code in set(ex_codes):
            # 检查是否也在 §4 接口设计中出现
            if code not in sec4_text:
                self.add_hint(
                    "exception_not_in_api",
                    "info",
                    "§7 异常处理",
                    f"异常 {code} 在 §4 接口设计中未作为错误码返回（系统/第三方异常通常不逐接口列举，属正常情况）",
                )

    def check_interface_consistency(self, sec4_text: str, sec13_text: str):
        """检查 §4 接口设计与 §13 接口清单是否一一对应"""
        # §4 中接口通常在反引号内，如 `POST /api/v1/orders`
        pattern_4 = r"`(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}:.-]+)`"
        paths_4 = set(re.findall(pattern_4, sec4_text))

        # §13 中接口在表格单元格内，格式如 `| 提交订单 | POST | /api/v1/orders | ... |`
        # 需要匹配方法列和路径列（中间有 | 分隔），路径可能被反引号包裹
        pattern_13 = r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*`?(/[\w/{}:.-]+)`?\s*\|"
        paths_13 = set(re.findall(pattern_13, sec13_text))

        missing_in_13 = paths_4 - paths_13
        missing_in_4 = paths_13 - paths_4
        for method, path in missing_in_13:
            self.add_issue(
                "interface_mismatch",
                "blocking",
                "§13 接口清单",
                f"§4 中存在接口 {method} {path}，但 §13 接口清单中缺失",
            )
        for method, path in missing_in_4:
            self.add_issue(
                "interface_mismatch",
                "blocking",
                "§4 接口设计",
                f"§13 接口清单中存在 {method} {path}，但 §4 中无详细定义",
            )


class UIAuditor(DocumentAuditor):
    """UI 设计文档审计器"""

    def run(self):
        self.check_required_sections([
            "设计系统引用", "页面布局", "组件样式", "状态展示", "与交互设计对应",
        ])

        # 页面编号格式由项目自定义，不硬编码连续性检查
        self.check_table_format()
        self.check_upstream_references()

        # 每个页面必须有默认/空/错误三种状态
        # 提取所有页面章节（一级标题匹配页面编号格式）
        page_nodes: List[List[MarkdownNode]] = []
        current_page: List[MarkdownNode] = []
        for n in self.nodes:
            if n.type == "heading" and re.search(r"§\d+\s+[A-Z]+-[A-Z]+-\d+", n.content):
                if current_page:
                    page_nodes.append(current_page)
                current_page = [n]
            elif current_page:
                current_page.append(n)
        if current_page:
            page_nodes.append(current_page)

        for page in page_nodes:
            page_title = page[0].content
            pm = re.search(r"([A-Z]+-[A-Z]+-\d+)", page_title)
            page_id = pm.group(1) if pm else "未知页面"

            # 在页面节点中查找 "状态展示" heading
            state_text = ""
            in_state_section = False
            state_heading_level = 6
            for n in page:
                if n.type == "heading" and "状态展示" in n.content:
                    in_state_section = True
                    state_heading_level = n.meta.get("level", 6)
                    continue
                if in_state_section:
                    if n.type == "heading" and n.meta.get("level", 1) <= state_heading_level:
                        break
                    if n.type == "table":
                        rows = n.meta.get("rows", [])
                        for row in rows:
                            state_text += " | ".join(row) + "\n"
                    else:
                        state_text += n.content + "\n"

            if not state_text:
                self.add_issue(
                    "missing_ui_state_section",
                    "blocking",
                    f"{page_id} 状态展示",
                    f"页面 {page_id} 缺少状态展示子节",
                )
                continue

            states = ["默认态", "悬停态", "按下态", "聚焦态", "禁用态", "加载态", "空状态", "错误状态", "成功状态", "骨架态"]
            missing = [s for s in states if s not in state_text]
            if missing:
                self.add_issue(
                    "missing_ui_state",
                    "blocking",
                    f"{page_id} 状态展示",
                    f"页面 {page_id} 缺少状态描述: {', '.join(missing)}",
                )


class TestAuditor(DocumentAuditor):
    """测试报告审计器"""

    def run(self):
        self.check_required_sections([
            "功能测试用例", "异常测试用例", "性能测试",
            "安全测试", "兼容性测试", "覆盖检查报告", "回归测试策略",
        ])

        sec1_text = self._section_text(r"§1\s+功能测试用例")
        sec2_text = self._section_text(r"§2\s+异常测试用例")

        # 测试用例编号格式完全由项目自定义，此处不做硬编码格式检查
        self.check_table_format()
        self.check_upstream_references()

        # §6 覆盖检查报告中每个验收标准在 §1/§2 中有对应用例
        sec6_text = self._section_text(r"§6\s+覆盖检查报告")
        all_cases = sec1_text + sec2_text
        # 验收标准编号格式由项目自定义（如 ACC-001），不硬编码为 §8.x
        # 从覆盖检查报告表格中提取验收标准编号（跳过表头、分隔行和空首列）
        sec6_table = self._extract_table_after(r"§6\s+覆盖检查报告")
        ac_ids = []
        if sec6_table:
            for row in sec6_table:
                if row and row[0].strip() and not re.match(r"^:?-+:?$", row[0]) \
                        and row[0].strip() not in ("验收标准编号", "编号", "ID"):
                    ac_ids.append(row[0].strip())
        for ac_id in ac_ids:
            if ac_id not in all_cases:
                self.add_issue(
                    "uncovered_acceptance",
                    "blocking",
                    "§6 覆盖检查报告",
                    f"验收标准 {ac_id} 在 §1/§2 中无对应测试用例",
                )

class GlobalPRDAuditor(DocumentAuditor):
    """PRD 顶层定义审计器"""

    def run(self):
        self.check_required_sections([
            "产品概述", "全局功能范围", "版本里程碑",
            "术语表", "状态值", "编码规则", "待决策问题",
        ])
        self.check_table_format()
        # check_error_code_format 需要传入 error_prefixes 参数，当前无项目级配置，暂不调用
        # self.check_error_code_format(error_prefixes=[...])

        # 检查是否出现"后续版本"等延迟占位（里程碑表除外）
        # 豁免：Skill 模板/写作指南中常出现这些词作为示例或说明
        body = self.raw_text
        if "AI 指令：此文件是 Skill 内部使用的" in body or "顶层定义模板（meta）" in body:
            pass  # 跳过模板文件的延迟占位检查
        else:
            # 去掉 §3 版本里程碑章节
            # 使用正则精确定位 heading 行，避免正文引用误匹配
            m_start = re.search(r"^##\s+§3\s+版本里程碑", body, re.MULTILINE)
            m_end = re.search(r"^##\s+§4\s+", body, re.MULTILINE)
            if m_start and m_end:
                body = body[:m_start.start()] + body[m_end.start():]
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
            "公共表定义", "全局接口约定", "全局安全规范", "基础设施",
        ])
        self.check_table_format()

        # 检查 §5.2 统一响应结构包含 code/message/data/traceId/timestamp
        sec25_text = self._section_text(r"§?5\.2.*响应结构|统一响应结构")
        missing_fields = []
        for field in ("code", "message", "data", "traceId", "timestamp"):
            if field not in sec25_text:
                missing_fields.append(field)
        if missing_fields:
            self.add_issue(
                "response_structure",
                "blocking",
                "§5.2 统一响应结构",
                f"未明确声明响应结构包含字段: {', '.join(missing_fields)}",
            )


# 错误码格式正则（模块级常量，统一标准）
ERROR_CODE_RE = r"[A-Z][A-Z_]*-[A-Z][A-Z_]*-\d+"

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
        if "上游文档" in text:
            # 优先在 upstream-document 表格区域内搜索，避免短文件名在正文误匹配
            # 先安全过滤掉围栏代码块，避免代码块内的 # 注释被误认为 heading
            text_no_code = re.sub(r"```[\s\S]*?```", "", text)
            upstream_match = re.search(
                r"上游文档.*?(?=^#{1,3}\s|\Z)", text_no_code, re.MULTILINE | re.DOTALL
            )
            search_area = upstream_match.group(0) if upstream_match else text_no_code
            scope_match = re.search(
                rf"\|\s*{re.escape(target_name)}\s*\|\s*[^|]+\|\s*([^|\n]+)\|",
                search_area,
            )
            if scope_match:
                scope = scope_match.group(1).strip()
                downstream.append({
                    "path": str(md_file.relative_to(docs_dir)),
                    "scope": scope,
                })
    return downstream


class GlobalInteractionAuditor(DocumentAuditor):
    """交互顶层定义审计器"""

    def run(self):
        self.check_required_sections([
            "交互令牌", "跨端通用规则", "交互状态规范",
            "交互反馈规范", "交互规范", "无障碍设计",
        ])
        self.check_table_format()

        # 检查 §3 交互状态规范包含 6 基础 + 4 异步状态
        sec3_text = self._section_text(r"§?3\s+(?:交互状态|交互状态规范)")
        base_states = ["默认态", "悬停态", "按下态", "聚焦态", "禁用态", "加载态"]
        async_states = ["空状态", "错误状态", "成功状态", "骨架态"]
        missing_base = [s for s in base_states if s not in sec3_text]
        missing_async = [s for s in async_states if s not in sec3_text]
        if missing_base:
            self.add_issue(
                "interaction_state_incomplete",
                "blocking",
                "§3 交互状态规范",
                f"缺少基础交互状态定义: {', '.join(missing_base)}",
            )
        if missing_async:
            self.add_issue(
                "interaction_state_incomplete",
                "blocking",
                "§3 交互状态规范",
                f"缺少异步/边界状态定义: {', '.join(missing_async)}",
            )

        # 检查 §4 交互反馈规范包含四类反馈时效红线
        sec4_text = self._section_text(r"§?4\s+(?:交互反馈|交互反馈规范)")
        feedback_types = ["点击响应", "弹窗出现", "页面切换", "异步提交"]
        missing_fb = [f for f in feedback_types if f not in sec4_text]
        if missing_fb:
            self.add_issue(
                "feedback_redline_missing",
                "warning",
                "§4 交互反馈规范",
                f"建议包含反馈时效红线: {', '.join(missing_fb)}",
            )


class GlobalUIAuditor(DocumentAuditor):
    """UI 顶层定义审计器"""

    def run(self):
        self.check_required_sections([
            "设计原则", "设计令牌体系", "色彩系统",
            "字体系统", "间距与布局系统", "形状系统",
            "阴影与海拔", "动效与过渡", "图标规范",
            "主题与暗黑模式", "组件库",
        ])
        self.check_table_format()

        # 检查 §11 组件库包含全局状态规范
        sec11_text = self._section_text(r"§?11\s+(?:组件库)")
        if "全局状态规范" not in sec11_text:
            self.add_issue(
                "ui_component_state_missing",
                "blocking",
                "§11 组件库",
                "组件库章节未声明全局状态规范",
            )


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
    "global-interaction": GlobalInteractionAuditor,
    "global-ui": GlobalUIAuditor,
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
    report = auditor.report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
