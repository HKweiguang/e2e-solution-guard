#!/usr/bin/env python3
"""
doc-audit.py — 产物一致性审计规则引擎（标准库 only）

核心抽象：
- Extractor: 从产物中提取结构化数据（章节、表格、编号、代码块）
- Rule: 接收提取的数据和上下文，执行检查，返回 Issue
- Engine: 按产物类型组合 Rule，执行并汇总

用法:
  python3 scripts/doc-audit.py <doc_path> --type prd --upstream up1.md up2.md
  python3 scripts/doc-audit.py <doc_path> --type prd --scan-downstream ./docs/
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
# 1. 数据模型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Issue:
    check_id: str
    severity: str  # blocking / warning / info
    location: str
    message: str


@dataclass
class ExtractedData:
    """提取后的结构化数据"""
    raw_text: str = ""
    sections: List[Tuple[int, str]] = field(default_factory=list)
    tables: List[List[List[str]]] = field(default_factory=list)
    code_blocks: List[Tuple[str, str]] = field(default_factory=list)
    # 产物类型特定的提取结果
    ids: Set[str] = field(default_factory=set)


@dataclass
class AuditContext:
    """审计上下文，包含上游文档提取的数据"""
    doc_path: Path
    doc_type: str
    upstream_docs: Dict[str, ExtractedData] = field(default_factory=dict)
    user_data: Dict[str, Any] = field(default_factory=dict)
    is_template: bool = False  # 产物模板豁免标记


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 提取层
# ═══════════════════════════════════════════════════════════════════════════════

class MarkdownExtractor:
    """基于状态机的轻量 Markdown 解析器。支持 heading / table / code / list / paragraph。"""

    def __init__(self, text: str):
        self.raw_text = text
        self.lines = text.splitlines()
        self.nodes: List[Dict[str, Any]] = []
        self._parse()

    def extract(self) -> ExtractedData:
        self._parse()
        data = ExtractedData(raw_text=self.raw_text)
        data.sections = self._extract_sections()
        data.tables = self._extract_tables()
        data.code_blocks = self._extract_code_blocks()
        data.ids = self._extract_ids()
        return data

    def _parse(self):
        """解析为节点列表，供后续精确提取使用"""
        pos = 0
        while pos < len(self.lines):
            line = self.lines[pos]
            stripped = line.strip()
            if not stripped:
                pos += 1
                continue
            if stripped.startswith("```"):
                self.nodes.append(self._parse_code_block(pos))
                pos = self.nodes[-1]["end_pos"]
            elif stripped.startswith("|"):
                self.nodes.append(self._parse_table(pos))
                pos = self.nodes[-1]["end_pos"]
            elif stripped.startswith("#"):
                self.nodes.append(self._parse_heading(pos))
                pos += 1
            else:
                pos += 1
        # 不解析 paragraph/list，因为我们主要用 heading/table/code

    def _parse_heading(self, pos: int) -> Dict:
        line = self.lines[pos].strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        level = len(m.group(1)) if m else 1
        text = m.group(2).strip() if m else line
        return {"type": "heading", "level": level, "text": text, "line": pos, "end_pos": pos + 1}

    def _parse_code_block(self, pos: int) -> Dict:
        fence = self.lines[pos].strip()
        lang = fence[3:].strip() if len(fence) > 3 else ""
        start = pos
        pos += 1
        lines: List[str] = []
        while pos < len(self.lines):
            if self.lines[pos].strip().startswith("```"):
                pos += 1
                break
            lines.append(self.lines[pos])
            pos += 1
        return {"type": "code", "lang": lang, "content": "\n".join(lines), "line": start, "end_pos": pos}

    def _parse_table(self, pos: int) -> Dict:
        rows: List[List[str]] = []
        start = pos
        while pos < len(self.lines):
            line = self.lines[pos].strip()
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line[1:].split("|")]
            if cells and not cells[-1]:
                cells.pop()
            rows.append(cells)
            pos += 1
        return {"type": "table", "rows": rows, "line": start, "end_pos": pos}

    def _extract_sections(self) -> List[Tuple[int, str]]:
        return [(n["level"], n["text"]) for n in self.nodes if n["type"] == "heading"]

    def _extract_tables(self) -> List[List[List[str]]]:
        return [n["rows"] for n in self.nodes if n["type"] == "table"]

    def _extract_code_blocks(self) -> List[Tuple[str, str]]:
        return [(n["lang"], n["content"]) for n in self.nodes if n["type"] == "code"]

    def _extract_ids(self) -> Set[str]:
        pattern = r"\b[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z][A-Za-z0-9_]*)*-\d+\b"
        return set(re.findall(pattern, self.raw_text))

    # ── 精细提取工具 ──

    def section_text(self, header_pattern: str) -> str:
        """提取匹配 header_pattern 的 heading 及其后的全部文本（直到同级或更高级 heading）"""
        lines = self.raw_text.splitlines()
        start_line = -1
        level = 6
        for i, line in enumerate(lines):
            m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if m and re.search(header_pattern, m.group(2).strip()):
                start_line = i
                level = len(m.group(1))
                break
        if start_line == -1:
            return ""

        parts: List[str] = []
        for line in lines[start_line + 1:]:
            m = re.match(r"^(#{1,6})\s+", line.strip())
            if m and len(m.group(1)) <= level:
                break
            parts.append(line)
        return "\n".join(parts).strip()

    def table_after_heading(self, header_pattern: str) -> Optional[List[List[str]]]:
        """在匹配 header_pattern 的 heading 后找到第一个 table"""
        found = False
        for n in self.nodes:
            if n["type"] == "heading" and re.search(header_pattern, n["text"]):
                found = True
                continue
            if found and n["type"] == "table":
                return n["rows"]
            if found and n["type"] == "heading" and n["level"] <= 2:
                break
        return None

    def all_tables_after_heading(self, header_pattern: str) -> List[List[List[str]]]:
        """在匹配 header_pattern 的 heading 后找到所有 table，直到同级或更高级 heading"""
        found = False
        tables: List[List[List[str]]] = []
        for n in self.nodes:
            if n["type"] == "heading" and re.search(header_pattern, n["text"]):
                found = True
                continue
            if found and n["type"] == "heading" and n["level"] <= 2:
                break
            if found and n["type"] == "table":
                tables.append(n["rows"])
        return tables

    def ids_in_section(self, header_pattern: str, id_pattern: Optional[str] = None) -> Set[str]:
        """从指定章节中提取编号"""
        text = self.section_text(header_pattern)
        if not text:
            return set()
        if id_pattern:
            return set(re.findall(id_pattern, text))
        # 默认模式
        return set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z][A-Za-z0-9_]*)*-\d+\b", text))

    def table_column_values(self, header_pattern: str, column_name: str) -> List[str]:
        """在匹配 header_pattern 的 heading 后的第一个表格中，提取指定列的所有数据值"""
        table = self.table_after_heading(header_pattern)
        if not table or len(table) < 2:
            return []
        header = [c.strip() for c in table[0]]
        if column_name not in header:
            return []
        col_idx = header.index(column_name)
        values = []
        for row in table[1:]:
            if len(row) <= col_idx:
                continue
            val = row[col_idx].strip()
            # 跳过分隔符行（如 :---:）
            if re.match(r"^:?-+:?$", val):
                continue
            values.append(val)
        return values


class HTMLExtractor:
    """从 UI HTML 产物中提取结构化数据"""

    def __init__(self, text: str):
        self.raw_text = text

    def extract(self) -> ExtractedData:
        data = ExtractedData(raw_text=self.raw_text)
        data.sections = self._extract_sections()
        data.ids = self._extract_classes()
        data.code_blocks = [("css", self._extract_css())]
        return data

    def _extract_sections(self) -> List[Tuple[int, str]]:
        sections = []
        for m in re.finditer(r'<section[^>]*id=["\']([^"\']+)["\']', self.raw_text):
            sections.append((2, m.group(1)))
        return sections

    def _extract_classes(self) -> Set[str]:
        classes: Set[str] = set()
        for m in re.finditer(r'class=["\']([^"\']+)["\']', self.raw_text):
            classes.update(m.group(1).split())
        return classes

    def _extract_css(self) -> str:
        blocks = re.findall(r"<style[^>]*>([\s\S]*?)</style>", self.raw_text)
        return "\n".join(blocks)

    def css_vars(self) -> Set[str]:
        css = self._extract_css()
        return set(re.findall(r"var\((--[\w-]+)\)", css))

    def has_doctype(self) -> bool:
        return bool(re.search(r"<!DOCTYPE\s+html", self.raw_text, re.IGNORECASE))

    def has_upstream_comment(self) -> bool:
        return bool(re.search(r"<!--\s*upstream:", self.raw_text))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 规则层
# ═══════════════════════════════════════════════════════════════════════════════

class Rule:
    """规则基类。子类覆盖 check() 方法。"""

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        raise NotImplementedError


# ── 通用规则 ──

class SectionExistsRule(Rule):
    """检查必填章节是否存在"""

    def __init__(self, check_id: str, patterns: List[str], severity: str = "blocking"):
        self.check_id = check_id
        self.patterns = patterns
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        headings = [s[1] for s in data.sections]
        issues = []
        for pattern in self.patterns:
            if not any(pattern in h for h in headings):
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location="章节结构", message=f"缺少必填章节: {pattern}"
                ))
        return issues


class TableFormatRule(Rule):
    """检查表格格式：列数一致、分隔行正确"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if len(table) < 2:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location=f"表格 #{idx}", message="表格少于两行，可能格式错误"
                ))
                continue
            sep = table[1]
            if not all(re.match(r"^:?-+:?$", cell) for cell in sep if cell.strip()):
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location=f"表格 #{idx}", message="第二行分隔线格式不正确"
                ))
            col_counts = [len(r) for r in table]
            if len(set(col_counts)) > 1:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location=f"表格 #{idx}", message=f"列数不一致: {col_counts}"
                ))
        return issues


class TableColumnRule(Rule):
    """检查指定表格是否包含必填列"""

    def __init__(self, check_id: str, header_pattern: str, required_cols: List[str],
                 severity: str = "blocking"):
        self.check_id = check_id
        self.header_pattern = header_pattern
        self.required_cols = required_cols
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(self.header_pattern)
        if not table or not table[0]:
            return [Issue(
                check_id=self.check_id, severity=self.severity,
                location="表格检查", message=f"未找到 '{self.header_pattern}' 后的表格"
            )]
        header = [c.strip() for c in table[0]]
        issues = []
        for col in self.required_cols:
            if col not in header:
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location=f"表格表头", message=f"缺少必填列: {col}"
                ))
        return issues


class IdDuplicateRule(Rule):
    """检查编号重复"""

    def __init__(self, check_id: str, id_pattern: Optional[str] = None):
        self.check_id = check_id
        self.id_pattern = id_pattern

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        ids = data.ids
        if self.id_pattern:
            ids = set(re.findall(self.id_pattern, data.raw_text))
        seen: Set[str] = set()
        issues = []
        for id_str in ids:
            if id_str in seen:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="编号重复", message=f"{id_str} 出现重复"
                ))
            seen.add(id_str)
        return issues


class IdContinuityRule(Rule):
    """检查编号连续性（按前缀分组）"""

    def __init__(self, check_id: str, id_pattern: Optional[str] = None):
        self.check_id = check_id
        self.id_pattern = id_pattern

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        ids = data.ids
        if self.id_pattern:
            ids = set(re.findall(self.id_pattern, data.raw_text))

        from collections import defaultdict
        groups = defaultdict(list)
        for id_str in ids:
            m = re.match(r"(.+)-(\d+)$", id_str)
            if m:
                groups[m.group(1)].append(int(m.group(2)))

        issues = []
        for prefix, nums in groups.items():
            nums = sorted(set(nums))
            for i in range(len(nums) - 1):
                if nums[i + 1] - nums[i] > 1:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location="编号连续性",
                        message=f"{prefix} 编号不连续，缺少 {prefix}-{nums[i]+1:03d}"
                    ))
        return issues


class IdFormatRule(Rule):
    """检查编号格式是否符合正则"""

    def __init__(self, check_id: str, format_pattern: str, id_pattern: Optional[str] = None):
        self.check_id = check_id
        self.format_pattern = format_pattern
        self.id_pattern = id_pattern

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        ids = data.ids
        if self.id_pattern:
            ids = set(re.findall(self.id_pattern, data.raw_text))
        issues = []
        for id_str in ids:
            if not re.match(self.format_pattern, id_str):
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="编号格式", message=f"{id_str} 格式不符合 {self.format_pattern}"
                ))
        return issues


class ReferenceExistsRule(Rule):
    """检查源集合中的每个元素是否在目标文本中存在"""

    def __init__(self, check_id: str, source_key: str, target_key: str,
                 severity: str = "blocking", message_template: str = "{item} 在目标中未找到"):
        self.check_id = check_id
        self.source_key = source_key
        self.target_key = target_key
        self.severity = severity
        self.message_template = message_template

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        source_items = ctx.user_data.get(self.source_key, set())
        target_text = ctx.user_data.get(self.target_key, "")
        issues = []
        for item in source_items:
            if item not in target_text:
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location="引用完整性", message=self.message_template.format(item=item)
                ))
        return issues


class SetAlignmentRule(Rule):
    """检查两个集合的关系：subset / equal / disjoint"""

    def __init__(self, check_id: str, set_a_key: str, set_b_key: str,
                 relation: str = "subset", severity: str = "blocking"):
        self.check_id = check_id
        self.set_a_key = set_a_key
        self.set_b_key = set_b_key
        self.relation = relation
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        set_a = ctx.user_data.get(self.set_a_key, set())
        set_b = ctx.user_data.get(self.set_b_key, set())
        issues = []

        if self.relation == "subset":
            missing = set_a - set_b
            if missing:
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location="集合对齐",
                    message=f"期望集合中缺失: {', '.join(sorted(missing))}"
                ))
        elif self.relation == "equal":
            if set_a != set_b:
                msgs = []
                if set_a - set_b:
                    msgs.append(f"A 有 B 无: {', '.join(sorted(set_a - set_b))}")
                if set_b - set_a:
                    msgs.append(f"B 有 A 无: {', '.join(sorted(set_b - set_a))}")
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location="集合对齐", message="; ".join(msgs)
                ))
        elif self.relation == "disjoint_check":
            # 检查 A 是否是 B 的子集（A 中的每个元素在 B 中有对应）
            missing = set_a - set_b
            if missing:
                issues.append(Issue(
                    check_id=self.check_id, severity=self.severity,
                    location="集合对齐",
                    message=f"未覆盖项: {', '.join(sorted(missing))}"
                ))
        return issues


class BidirectionalMappingRule(Rule):
    """双向映射完整性检查：检查当前文档与上游 PRD 之间的功能点编号映射是否完整

    正向（PRD → 当前）：PRD §3 功能需求中的功能编号是否在技术方案中有对应引用
    反向（当前 → PRD）：技术方案中引用的功能点编号是否在 PRD 中存在
    """

    def __init__(self, check_id: str,
                 upstream_file_hint: str = "prd",
                 forward_severity: str = "warning",
                 reverse_severity: str = "warning"):
        self.check_id = check_id
        self.upstream_file_hint = upstream_file_hint
        self.forward_severity = forward_severity
        self.reverse_severity = reverse_severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        issues = []

        # 1. 查找上游 PRD
        upstream_data = self._find_upstream(ctx)
        if not upstream_data:
            return issues

        # 2. 从 PRD §3 功能需求表格提取「功能编号」列
        prd_extractor = MarkdownExtractor(upstream_data.raw_text)
        prd_feature_ids = set(prd_extractor.table_column_values(r"§3\s+功能需求", "功能编号"))
        # 回退：从全文正则提取（当表格无"功能编号"列时）
        if not prd_feature_ids:
            prd_feature_ids = set(re.findall(
                r"\b[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+\b",
                upstream_data.raw_text
            ))

        # 3. 从当前文档提取功能点引用
        tech_extractor = MarkdownExtractor(data.raw_text)
        tech_feature_ids: Set[str] = set()
        # §4 接口设计的「对应功能点」列
        tech_feature_ids.update(tech_extractor.table_column_values(r"§4\s+接口设计", "对应功能点"))
        # §13 接口清单的「对应功能点」列
        tech_feature_ids.update(tech_extractor.table_column_values(r"§13\s+接口清单", "对应功能点"))
        # 头部「覆盖功能点」行
        header_match = re.search(r"\*\*覆盖功能点\*\*[:：]?\s*(.+?)(?:\n|$)", data.raw_text)
        if header_match:
            tech_feature_ids.update(re.findall(
                r"\b[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+\b",
                header_match.group(1)
            ))

        # 4. 正向检查：PRD 有但当前文档没有
        missing_in_current = prd_feature_ids - tech_feature_ids
        for fp_id in missing_in_current:
            issues.append(Issue(
                check_id=self.check_id,
                severity=self.forward_severity,
                location="双向映射",
                message=f"PRD 功能点 {fp_id} 在技术方案中无对应引用"
            ))

        # 5. 反向检查：当前文档有但 PRD 没有
        missing_in_prd = tech_feature_ids - prd_feature_ids
        for fp_id in missing_in_prd:
            issues.append(Issue(
                check_id=self.check_id,
                severity=self.reverse_severity,
                location="双向映射",
                message=f"技术方案引用了 PRD 中不存在的需求 {fp_id}"
            ))

        return issues

    def _find_upstream(self, ctx: AuditContext) -> Optional[ExtractedData]:
        for path, up_data in ctx.upstream_docs.items():
            if self.upstream_file_hint.lower() in path.lower():
                return up_data
        return None


class CrossDocTerminologyRule(Rule):
    """跨产物术语一致性检查：从上游 PRD-顶层定义的术语表中提取「禁止别名」，
    检查当前文档中是否使用了禁止别名。"""

    def __init__(self, check_id: str,
                 upstream_file_hint: str = "prd-top-level",
                 severity: str = "warning"):
        self.check_id = check_id
        self.upstream_file_hint = upstream_file_hint
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []

        # 1. 查找上游 PRD-顶层定义
        upstream_data = self._find_upstream(ctx)
        if not upstream_data:
            return []

        # 2. 从 PRD-顶层定义 §4 术语表提取「禁止别名」
        extractor = MarkdownExtractor(upstream_data.raw_text)
        table = extractor.table_after_heading(r"§4\s+术语表")
        if not table or len(table) < 2:
            return []

        header = [c.strip() for c in table[0]]
        if "术语" not in header or "禁止别名" not in header:
            return []

        term_idx = header.index("术语")
        alias_idx = header.index("禁止别名")

        forbidden_aliases: Dict[str, str] = {}  # 禁止别名 -> 标准术语
        for row in table[1:]:
            if len(row) <= max(term_idx, alias_idx):
                continue
            term = row[term_idx].strip()
            alias_text = row[alias_idx].strip()
            # 跳过分隔符行（如 :---:）
            if re.match(r"^:?-+:?$", term) or re.match(r"^:?-+:?$", alias_text):
                continue
            # 提取引号内的别名（支持中文/英文引号）
            aliases = re.findall(r'[""''""'']([^""''""'']+)[""''""'']', alias_text)
            if not aliases:
                # 回退：按常见分隔符拆分
                aliases = re.split(r"[，,、；;]", alias_text)
            for alias in aliases:
                alias = alias.strip()
                alias = re.sub(r"^(不可称|禁止称|不要称|避免使用)[\"'\"'\"'\"'\"'\"']?", "", alias).strip()
                alias = re.sub(r"[\"'\"'\"'\"'\"'\"']$", "", alias).strip()
                if alias and alias not in ("—", "-", "", "无"):
                    forbidden_aliases[alias] = term

        if not forbidden_aliases:
            return []

        # 3. 检查当前文档中是否出现了禁止别名
        issues = []
        text = data.raw_text
        for alias, standard_term in sorted(forbidden_aliases.items(), key=lambda x: -len(x[0])):
            # 中文无空格分词，采用「前后非同类字符」作为边界：
            # 前面是字符串开头、空格、标点；后面同理。
            # 对于多字别名（常见情况），直接精确匹配即可，误报率极低。
            escaped = re.escape(alias)
            if len(alias) >= 2:
                pattern = escaped
            else:
                # 单字别名需要更严格的边界
                pattern = r"(?<![\u4e00-\u9fa5a-zA-Z0-9])" + escaped + r"(?![\u4e00-\u9fa5a-zA-Z0-9])"
            for m in re.finditer(pattern, text):
                start = max(0, m.start() - 30)
                end = min(len(text), m.end() + 30)
                context = text[start:end].replace("\n", " ")
                issues.append(Issue(
                    check_id=self.check_id,
                    severity=self.severity,
                    location="术语一致性",
                    message=f"发现禁止别名「{alias}」（标准术语应为「{standard_term}」），上下文: ...{context}..."
                ))
        return issues

    def _find_upstream(self, ctx: AuditContext) -> Optional[ExtractedData]:
        for path, up_data in ctx.upstream_docs.items():
            if self.upstream_file_hint.lower() in path.lower():
                return up_data
        # 回退：找任何包含 "prd" 且路径中包含 "top" 的 upstream
        for path, up_data in ctx.upstream_docs.items():
            if "prd" in path.lower() and ("top" in path.lower() or "顶层" in path):
                return up_data
        return None


class BrokenInternalLinkRule(Rule):
    """检查文档内部的 §x 交叉引用是否指向存在的章节"""

    def __init__(self, check_id: str, severity: str = "warning"):
        self.check_id = check_id
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []

        # 1. 提取文档中所有 §x 引用（如 §3、§4.2、§2.1.3）
        ref_pattern = r"§(\d+(?:\.\d+)*)"
        refs = set(re.findall(ref_pattern, data.raw_text))

        # 2. 提取文档中实际存在的章节编号
        actual_sections: Set[str] = set()
        for level, title in data.sections:
            m = re.search(r"§(\d+(?:\.\d+)*)\s", title)
            if m:
                actual_sections.add(m.group(1))

        # 3. 检查每个引用是否存在（精确匹配或作为前缀）
        issues = []
        for ref in sorted(refs, key=lambda x: list(map(int, x.split(".")))):
            if not self._section_exists(ref, actual_sections):
                issues.append(Issue(
                    check_id=self.check_id,
                    severity=self.severity,
                    location="内部引用",
                    message=f"引用 §{ref} 在文档中不存在"
                ))
        return issues

    @staticmethod
    def _section_exists(ref: str, actual_sections: Set[str]) -> bool:
        if ref in actual_sections:
            return True
        # 检查是否有以 ref + "." 开头的子章节
        for sec in actual_sections:
            if sec.startswith(ref + "."):
                return True
        return False


class ResponsiveBreakpointRule(Rule):
    """检查 UI HTML 中的 @media 断点是否与 UI-顶层定义一致"""

    def __init__(self, check_id: str,
                 upstream_file_hint: str = "ui-top-level",
                 severity: str = "warning"):
        self.check_id = check_id
        self.upstream_file_hint = upstream_file_hint
        self.severity = severity

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []

        # 1. 查找上游 UI-顶层定义
        upstream_data = self._find_upstream(ctx)
        if not upstream_data:
            return []

        # 2. 从 UI-顶层定义 §2.5.5 提取断点数值
        extractor = MarkdownExtractor(upstream_data.raw_text)
        table = extractor.table_after_heading(r"§2\.5\.5\s+响应式断点")
        if not table or len(table) < 2:
            return []

        header = [c.strip() for c in table[0]]
        if "范围" not in header:
            return []

        range_idx = header.index("范围")
        expected_breakpoints: Set[str] = set()
        for row in table[1:]:
            if len(row) <= range_idx:
                continue
            range_val = row[range_idx].strip()
            if re.match(r"^:?-+:?$", range_val):
                continue
            nums = re.findall(r"\d+", range_val)
            expected_breakpoints.update(nums)

        if not expected_breakpoints:
            return []

        # 3. 从 HTML 中提取 @media 断点
        html_breakpoints: Set[str] = set()
        for m in re.finditer(r"@media\s*\([^)]*?width\s*[:<>=]+\s*(\d+)px", data.raw_text):
            html_breakpoints.add(m.group(1))

        # 4. 比对
        issues = []
        missing_in_html = expected_breakpoints - html_breakpoints
        for bp in sorted(missing_in_html, key=int):
            issues.append(Issue(
                check_id=self.check_id,
                severity=self.severity,
                location="响应式断点",
                message=f"UI-顶层定义声明的断点 {bp}px 在 HTML 中未找到对应的 @media 查询"
            ))

        extra_in_html = html_breakpoints - expected_breakpoints
        for bp in sorted(extra_in_html, key=int):
            issues.append(Issue(
                check_id=self.check_id,
                severity="info",
                location="响应式断点",
                message=f"HTML 中使用了 UI-顶层定义未声明的断点 {bp}px"
            ))

        return issues

    def _find_upstream(self, ctx: AuditContext) -> Optional[ExtractedData]:
        for path, up_data in ctx.upstream_docs.items():
            if self.upstream_file_hint.lower() in path.lower():
                return up_data
        return None


class RegexMatchRule(Rule):
    """检查文本是否匹配（或不应匹配）正则"""

    def __init__(self, check_id: str, pattern: str, text_key: str,
                 should_match: bool = True, severity: str = "blocking", message: str = ""):
        self.check_id = check_id
        self.pattern = pattern
        self.text_key = text_key
        self.should_match = should_match
        self.severity = severity
        self.message = message

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        text = ctx.user_data.get(self.text_key, data.raw_text)
        matched = bool(re.search(self.pattern, text))
        if matched != self.should_match:
            return [Issue(
                check_id=self.check_id, severity=self.severity,
                location="格式检查", message=self.message
            )]
        return []


class UpstreamRefRule(Rule):
    """检查 upstream-document 表格是否存在且引用的文档可找到"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        issues = []

        # 豁免：Skill 模板中的 upstream-document 仅为示例
        if "不要机械套用" in data.raw_text:
            return issues

        # HTML 产物：检查 <!-- upstream: ... --> 注释
        if ctx.doc_path.suffix == ".html":
            if not re.search(r"<!--\s*upstream:", data.raw_text, re.I):
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="文件头部", message="缺少 upstream-document 声明（<!-- upstream: ... -->）"
                ))
            return issues

        # Markdown 产物
        if "上游文档" not in data.raw_text:
            issues.append(Issue(
                check_id=self.check_id, severity="blocking",
                location="文件头部", message="缺少 upstream-document 声明"
            ))
            return issues

        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(r"上游文档")
        # 回退：支持 **上游文档** 加粗形式（非 heading）
        if not table:
            table = self._table_after_keyword(data.raw_text, "上游文档")
        if not table or len(table) < 2:
            issues.append(Issue(
                check_id=self.check_id, severity="blocking",
                location="文件头部", message="upstream-document 表格格式错误或为空"
            ))
            return issues

        doc_dir = ctx.doc_path.parent
        for row in table[1:]:
            if len(row) < 1:
                continue
            doc_name = row[0].strip()
            if re.match(r"^:?-+:?$", doc_name):
                continue
            possible = [doc_name, doc_name + ".md"]
            found = any((doc_dir / name).exists() for name in possible)
            if not found and "规范" not in doc_name and "AGENTS" not in doc_name:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="文件头部",
                    message=f"上游文档 '{doc_name}' 在当前目录未找到，请确认路径"
                ))
        return issues

    @staticmethod
    def _table_after_keyword(text: str, keyword: str) -> Optional[List[List[str]]]:
        """在 keyword 后的文本中查找第一个 Markdown 表格（非 heading 形式）。"""
        idx = text.find(keyword)
        if idx == -1:
            return None
        after = text[idx + len(keyword):]
        lines = after.splitlines()
        table_lines = []
        in_table = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                in_table = True
                table_lines.append(stripped)
            elif in_table and not stripped:
                continue  # 允许表格中的空行
            elif in_table:
                break
        if len(table_lines) < 2:
            return None
        rows = []
        for tl in table_lines:
            cells = [c.strip() for c in tl[1:].split("|")]
            if cells and not cells[-1]:
                cells.pop()
            rows.append(cells)
        return rows


# ── 专用规则（产物类型特定）──

class FeatureTableColumnsRule(Rule):
    """PRD: 检查 §3 功能需求表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(r"§3\s+功能需求")
        if not table or len(table) < 2:
            return [Issue(check_id=self.check_id, severity="blocking",
                          location="§3 功能需求", message="未找到功能需求表格")]
        header = [c.strip() for c in table[0]]
        issues = []
        for col in self.required_cols:
            if col not in header:
                issues.append(Issue(check_id=self.check_id, severity="blocking",
                                    location="§3 功能需求表头",
                                    message=f"缺少必填列: {col}"))
        return issues


class AcceptanceFeatureRefRule(Rule):
    """PRD: 检查 §8 每条验收标准是否对应 §3 的功能点"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        # 提取 §3 功能编号（表格第一列，跳过表头）
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        feature_ids = set()
        if sec3_table and len(sec3_table) > 1:
            for row in sec3_table[1:]:
                if row and not re.match(r"^:?-+:?$", row[0]):
                    feature_ids.add(row[0].strip())

        # 提取 §8 验收标准表格
        sec8_table = extractor.table_after_heading(r"§8\s+验收标准")
        issues = []
        if not sec8_table or len(sec8_table) < 2:
            return issues

        for row in sec8_table[1:]:
            if not row or re.match(r"^:?-+:?$", row[0]):
                continue
            ac_id = row[0].strip()
            # 检查第二列（功能编号列）或整行中是否有功能点
            has_ref = False
            feature_col = row[1].strip() if len(row) > 1 else ""
            if feature_col and feature_ids:
                parts = re.split(r"[,，;；\s|]+", feature_col)
                has_ref = any(fid == part for part in parts for fid in feature_ids)
            if not has_ref and feature_ids:
                row_text = " | ".join(row[1:]) if len(row) > 1 else ""
                has_ref = any(fid in row_text for fid in feature_ids)
            if not has_ref and feature_ids:
                issues.append(Issue(check_id=self.check_id, severity="blocking",
                                    location="§8 验收标准",
                                    message=f"验收项 {ac_id} 未关联任何功能点"))
        return issues


class P0AcceptanceRule(Rule):
    """PRD: 检查 §3 中标记为 P0 的功能是否在 §8 有验收标准"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        p0_features = []
        if sec3_table and len(sec3_table) > 1:
            for row in sec3_table[1:]:
                if not row or re.match(r"^:?-+:?$", row[0]):
                    continue
                # 查找优先级列（通常包含 P0/P1/P2）
                row_text = " | ".join(row)
                if "P0" in row_text:
                    p0_features.append(row[0].strip())

        sec8_text = extractor.section_text(r"§8\s+验收标准")
        issues = []
        for fid in p0_features:
            if fid not in sec8_text:
                issues.append(Issue(check_id=self.check_id, severity="blocking",
                                    location="§8 验收标准",
                                    message=f"P0 功能点 {fid} 在 §8 中无对应验收标准"))
        return issues


class InternalRefRule(Rule):
    """PRD: 检查 §3 功能编号是否在 §6/§7/§8 中被引用"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        feature_ids = set()
        if sec3_table and len(sec3_table) > 1:
            for row in sec3_table[1:]:
                if row and not re.match(r"^:?-+:?$", row[0]):
                    feature_ids.add(row[0].strip())

        downstream_text = (extractor.section_text(r"§6\s+业务规则") +
                           extractor.section_text(r"§7\s+错误处理") +
                           extractor.section_text(r"§8\s+验收标准"))
        issues = []
        for fid in feature_ids:
            if fid not in downstream_text:
                issues.append(Issue(check_id=self.check_id, severity="warning",
                                    location="内部自洽性",
                                    message=f"功能点 {fid} 在 §6/§7/§8 中未被引用"))
        return issues


class ReverseFeatureRefRule(Rule):
    """PRD: 反向检查——指定章节中引用的编号是否在 §3 功能需求中存在"""

    def __init__(self, check_id: str, source_section_pattern: str, location_name: str):
        self.check_id = check_id
        self.source_section_pattern = source_section_pattern
        self.location_name = location_name

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        # 1. 从 §3 提取功能编号集合
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        feature_ids: Set[str] = set()
        if sec3_table and len(sec3_table) > 1:
            for row in sec3_table[1:]:
                if row and not re.match(r"^:?-+:?$", row[0]):
                    feature_ids.add(row[0].strip())
        if not feature_ids:
            return []

        # 2. 从源章节提取所有编号引用
        source_text = extractor.section_text(self.source_section_pattern)
        if not source_text:
            return []

        # 提取所有编号，然后过滤掉明显不是功能编号的（ERR/PAGE/RULE 前缀）
        all_refs = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+\b", source_text))
        non_feature_prefixes = {"ERR", "E", "PAGE", "P", "RULE", "R"}
        refs = set()
        for ref in all_refs:
            first_part = ref.split("-")[0]
            if first_part not in non_feature_prefixes:
                refs.add(ref)

        # 3. 报告在 §3 中不存在的引用
        issues = []
        for ref in sorted(refs):
            if ref not in feature_ids:
                issues.append(Issue(
                    check_id=self.check_id,
                    severity="warning",
                    location=self.location_name,
                    message=f"{self.location_name} 引用了 §3 中不存在的需求 {ref}"
                ))
        return issues


class PageStructureRule(Rule):
    """交互设计: 检查每个页面是否包含指定的必含子节"""

    def __init__(self, check_id: str, required_subsections: List[str], skip_first_page: bool = True):
        self.check_id = check_id
        self.required_subsections = required_subsections
        self.skip_first_page = skip_first_page

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        # 收集所有一级章节（页面）
        pages = []
        for i, n in enumerate(extractor.nodes):
            if n["type"] == "heading" and n["level"] == 1:
                pages.append((i, n["text"]))

        if self.skip_first_page and len(pages) > 1:
            pages = pages[1:]

        issues = []
        for page_idx, page_title in pages:
            # 收集该页面下的所有子节标题（level >= 2）
            subsections: List[str] = []
            for n in extractor.nodes[page_idx + 1:]:
                if n["type"] == "heading" and n["level"] <= 1:
                    break
                if n["type"] == "heading":
                    subsections.append(n["text"])

            for required in self.required_subsections:
                found = any(required in sub for sub in subsections)
                if not found:
                    issues.append(Issue(
                        check_id=self.check_id,
                        severity="blocking",
                        location=f"页面 {page_title}",
                        message=f"页面 {page_title} 缺少必含子节: {required}"
                    ))
        return issues


class IdFormatConsistencyRule(Rule):
    """PRD: 检查 §3 功能编号的前缀是否一致（统一模块/角色前缀）"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        if not sec3_table or len(sec3_table) < 2:
            return []

        prefixes: Set[str] = set()
        for row in sec3_table[1:]:
            if not row or re.match(r"^:?-+:?$", row[0]):
                continue
            fid = row[0].strip()
            m = re.match(r"(.+)-\d+$", fid)
            if m:
                prefixes.add(m.group(1))

        if len(prefixes) > 1:
            return [Issue(
                check_id=self.check_id,
                severity="warning",
                location="§3 功能编号",
                message=f"功能编号前缀不一致，发现 {len(prefixes)} 种前缀: {', '.join(sorted(prefixes))}"
            )]
        return []


class PagePrefixConsistencyRule(Rule):
    """交互设计: 检查页面编号前缀是否一致"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        # 从一级章节标题中提取页面编号
        page_ids: List[str] = []
        for n in extractor.nodes:
            if n["type"] == "heading" and n["level"] == 1:
                m = re.search(r"\b([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)\b", n["text"])
                if m:
                    page_ids.append(m.group(1))

        if not page_ids:
            return []

        prefixes: Set[str] = set()
        for pid in page_ids:
            first_part = pid.split("-")[0]
            prefixes.add(first_part)

        if len(prefixes) > 1:
            return [Issue(
                check_id=self.check_id,
                severity="warning",
                location="页面编号",
                message=f"页面编号前缀不一致，发现 {len(prefixes)} 种前缀: {', '.join(sorted(prefixes))}"
            )]
        return []


class PageCoverageRule(Rule):
    """UI: 检查 HTML 的 section id 是否覆盖上游交互设计的页面编号"""

    def __init__(self, check_id: str, upstream_file_hint: str = "interaction"):
        self.check_id = check_id
        self.upstream_file_hint = upstream_file_hint

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []

        upstream_data = self._find_upstream(ctx)
        if not upstream_data:
            return []

        # 从交互设计提取页面编号
        upstream_ids: Set[str] = set()
        for n in upstream_data.sections:
            level, title = n
            if level == 1:
                m = re.search(r"\b(PAGE-[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)\b", title)
                if m:
                    upstream_ids.add(m.group(1))

        if not upstream_ids:
            return []

        # 从 HTML 提取 section id
        html_ids = set(re.findall(r'<section[^>]*id=["\']([^"\']+)["\']', data.raw_text))

        issues = []
        missing = upstream_ids - html_ids
        for pid in sorted(missing):
            issues.append(Issue(
                check_id=self.check_id,
                severity="warning",
                location="页面覆盖度",
                message=f"交互设计页面 {pid} 在 UI HTML 中无对应 section id"
            ))
        return issues

    def _find_upstream(self, ctx: AuditContext) -> Optional[ExtractedData]:
        for path, up_data in ctx.upstream_docs.items():
            if self.upstream_file_hint.lower() in path.lower():
                return up_data
        return None


class TableColumnCompletenessRule(Rule):
    """技术方案: 检查 §3 数据模型表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§3\s+数据模型")
        issues = []
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if re.match(r"^:?-+:?$", header[0]):
                continue
            for col in self.required_cols:
                if col not in header:
                    issues.append(Issue(
                        check_id=self.check_id,
                        severity="blocking",
                        location="数据模型表头",
                        message=f"表格缺少必填列: {col}"
                    ))
        return issues


class InterfaceTestCoverageRule(Rule):
    """测试方案: 检查技术方案的接口是否在测试用例中有覆盖"""

    def __init__(self, check_id: str, upstream_file_hint: str = "tech"):
        self.check_id = check_id
        self.upstream_file_hint = upstream_file_hint

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []

        upstream_data = self._find_upstream(ctx)
        if not upstream_data:
            return []

        # 从 Tech §13 提取接口列表
        tech_extractor = MarkdownExtractor(upstream_data.raw_text)
        table = tech_extractor.table_after_heading(r"§13\s+接口清单")
        tech_interfaces: Set[Tuple[str, str]] = set()
        if table and len(table) >= 2:
            header = [c.strip() for c in table[0]]
            method_idx = self._idx(header, ["方法", "HTTP 方法"])
            path_idx = self._idx(header, ["路径", "URL", "接口路径"])
            if method_idx is not None and path_idx is not None:
                for row in table[1:]:
                    if len(row) <= max(method_idx, path_idx):
                        continue
                    if re.match(r"^:?-+:?$", row[0]):
                        continue
                    method = row[method_idx].strip().strip("`\"'")
                    path = row[path_idx].strip().strip("`\"'")
                    if path:
                        tech_interfaces.add((method, path))

        if not tech_interfaces:
            return []

        # 从测试文档全文中搜索接口引用
        test_text = data.raw_text
        issues = []
        for method, path in sorted(tech_interfaces):
            # 搜索方法（单词边界）和路径（空白边界）
            found = False
            if re.search(r"\b" + re.escape(method) + r"\b", test_text) and re.search(r"(?<!\S)" + re.escape(path) + r"(?!\S)", test_text):
                found = True
            if not found:
                issues.append(Issue(
                    check_id=self.check_id,
                    severity="warning",
                    location="接口测试覆盖",
                    message=f"技术方案接口 {method} {path} 在测试用例中未找到覆盖"
                ))
        return issues

    def _find_upstream(self, ctx: AuditContext) -> Optional[ExtractedData]:
        for path, up_data in ctx.upstream_docs.items():
            if self.upstream_file_hint.lower() in path.lower():
                return up_data
        return None

    @staticmethod
    def _idx(header: List[str], candidates: List[str]) -> Optional[int]:
        for c in candidates:
            if c in header:
                return header.index(c)
        return None


class SVGExistRule(Rule):
    """交互设计: 检查每个页面是否包含 SVG 线框图"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        # 遍历所有页面章节（一级标题匹配页面编号格式）
        issues = []
        in_page = False
        page_title = ""
        page_content = ""
        for line in extractor.lines:
            if re.search(r"^##\s+§\d+\s+[A-Z]+(?:-[A-Z]+)*-\d+", line):
                if in_page and "<svg" not in page_content:
                    issues.append(Issue(check_id=self.check_id, severity="blocking",
                                        location=page_title, message="页面缺少 SVG 线框图"))
                in_page = True
                page_title = line.strip()
                page_content = ""
            elif in_page:
                page_content += line + "\n"
        # 检查最后一个页面
        if in_page and "<svg" not in page_content:
            issues.append(Issue(check_id=self.check_id, severity="blocking",
                                location=page_title, message="页面缺少 SVG 线框图"))
        return issues


class StateMatrixRule(Rule):
    """交互设计: 检查组件状态矩阵是否包含指定列数"""

    def __init__(self, check_id: str, expected_cols: int, col_name: str = ""):
        self.check_id = check_id
        self.expected_cols = expected_cols
        self.col_name = col_name

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            # 识别状态矩阵：表头包含"默认"或"默认态"
            if any("默认" in h for h in header):
                if len(header) < self.expected_cols:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location=f"状态矩阵 #{idx}",
                        message=f"状态矩阵只有 {len(header)} 列，应为至少 {self.expected_cols} 列"
                    ))
        return issues


class PageFlowColumnsRule(Rule):
    """交互设计: 检查页面流程表格是否包含指定列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            # 识别页面流程表：包含"前置条件"或"用户操作"
            if any("前置条件" in h or "用户操作" in h for h in header):
                for col in self.required_cols:
                    if col not in header:
                        issues.append(Issue(
                            check_id=self.check_id, severity="blocking",
                            location=f"页面流程 #{idx}",
                            message=f"缺少必填列: {col}"
                        ))
        return issues


class ExceptionColumnsRule(Rule):
    """交互设计: 检查异常处理表格是否包含指定列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            # 识别异常处理表：包含"异常场景"或"触发条件"
            if any("异常场景" in h or "触发条件" in h for h in header):
                for col in self.required_cols:
                    if col not in header:
                        issues.append(Issue(
                            check_id=self.check_id, severity="blocking",
                            location=f"异常处理 #{idx}",
                            message=f"缺少必填列: {col}"
                        ))
        return issues


class UIStateMapRule(Rule):
    """UI: 检查状态映射表是否包含 4 个字段"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            # 识别状态映射表：包含"交互状态"
            if any("交互状态" in h for h in header):
                if len(header) < 4:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location=f"状态映射表 #{idx}",
                        message=f"状态映射表只有 {len(header)} 列，应为 4 列（交互状态 / CSS 类/伪类 / Token 变量 / 技术方案引用）"
                    ))
        return issues


class UIClassConsistencyRule(Rule):
    """UI: 检查状态映射表中的 CSS 类名是否在 HTML 中存在"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        extractor = MarkdownExtractor(data.raw_text)
        # 从所有表格中提取 CSS 类名（交互状态列和 CSS 类/伪类列）
        map_classes = set()
        for table in data.tables:
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            if not any("交互状态" in h for h in header):
                continue
            css_idx = -1
            for i, h in enumerate(header):
                if "CSS" in h or "类" in h:
                    css_idx = i
                    break
            if css_idx < 0:
                continue
            for row in table[2:]:
                if len(row) > css_idx:
                    val = row[css_idx].strip()
                    # 提取类名，如 :hover → hover, .disabled → disabled
                    for cls in re.findall(r'\.([\w-]+)', val):
                        map_classes.add(cls)
                    for pseudo in re.findall(r':([\w-]+)', val):
                        map_classes.add(pseudo)

        # 从 HTML 中提取 class 属性
        html_classes = set()
        for m in re.finditer(r'class=["\']([^"\']+)["\']', data.raw_text):
            html_classes.update(m.group(1).split())
        for m in re.finditer(r'<(\w+)[^>]*>', data.raw_text):
            tag = m.group(1)
            if tag in ("section", "div", "span", "button", "input"):
                # 从标签中提取可能的状态类
                pass  # 已由 class 属性捕获

        missing = map_classes - html_classes
        issues = []
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="CSS 类一致性",
                message=f"状态映射表中的类在 HTML 中未找到: {', '.join(sorted(missing))}"
            ))
        return issues


class StateStyleExistRule(Rule):
    """UI: 检查 HTML 中是否包含关键状态样式类/伪类"""

    def __init__(self, check_id: str, required_states: List[str]):
        self.check_id = check_id
        self.required_states = required_states

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        css = ""
        for lang, content in data.code_blocks:
            if lang in ("css", "", "html") or "style" in lang.lower():
                css += content + "\n"
        # 如果没有 code block，尝试从 HTML 中提取 style 标签内容
        if not css:
            css_match = re.search(r"<style[^>]*>([\s\S]*?)</style>", data.raw_text)
            if css_match:
                css = css_match.group(1)

        issues = []
        for state in self.required_states:
            pattern = rf"\.{re.escape(state)}\b|:{re.escape(state)}\b"
            if not re.search(pattern, css):
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="CSS 状态样式",
                    message=f"缺少状态样式: {state}"
                ))
        return issues


class InterfaceInventoryMatchRule(Rule):
    """技术方案: 检查 §13 接口清单与 §4 接口设计是否一一对应"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        sec4_interfaces = self._extract_sec4_interfaces(extractor)
        sec13_interfaces = self._extract_sec13_interfaces(extractor)

        if not sec4_interfaces and not sec13_interfaces:
            return []

        issues = []
        missing_in_13 = sec4_interfaces - sec13_interfaces
        for method, path in missing_in_13:
            issues.append(Issue(
                check_id=self.check_id, severity="blocking",
                location="接口一致性",
                message=f"§4 接口设计中的 {method} {path} 在 §13 接口清单中未找到"
            ))

        extra_in_13 = sec13_interfaces - sec4_interfaces
        for method, path in extra_in_13:
            issues.append(Issue(
                check_id=self.check_id, severity="blocking",
                location="接口一致性",
                message=f"§13 接口清单中的 {method} {path} 在 §4 接口设计中未找到"
            ))
        return issues

    def _extract_sec4_interfaces(self, extractor: MarkdownExtractor) -> Set[Tuple[str, str]]:
        interfaces: Set[Tuple[str, str]] = set()
        tables = extractor.all_tables_after_heading(r"§4\s+接口设计")
        for table in tables:
            if not table or len(table) < 2:
                continue
            first_col = [row[0].strip() for row in table if row]
            is_vertical = any(v in ("URL", "路径", "方法", "功能") for v in first_col)
            if is_vertical:
                url = method = ""
                for row in table:
                    if len(row) < 2:
                        continue
                    field = row[0].strip()
                    value = row[1].strip()
                    # 跳过分隔符行
                    if re.match(r"^:?-+:?$", field) or re.match(r"^:?-+:?$", value):
                        continue
                    if field in ("URL", "路径"):
                        url = value
                    elif field == "方法":
                        method = value
                if url:
                    m = re.match(r"[`\"']?([A-Z]+)\s+(\S+)[`\"']?", url)
                    if m:
                        method = m.group(1)
                        path = m.group(2).strip("`\"'")
                    else:
                        path = url.strip("`\"'")
                    if path:
                        interfaces.add((method or "?", path))
            else:
                header = [c.strip() for c in table[0]]
                method_idx = self._idx(header, ["方法", "HTTP 方法"])
                path_idx = self._idx(header, ["URL", "路径", "接口路径"])
                if method_idx is not None and path_idx is not None:
                    for row in table[1:]:
                        if len(row) <= max(method_idx, path_idx):
                            continue
                        if re.match(r"^:?-+:?$", row[0]):
                            continue
                        method = row[method_idx].strip().strip("`\"'")
                        path = row[path_idx].strip().strip("`\"'")
                        if path:
                            interfaces.add((method, path))
        return interfaces

    def _extract_sec13_interfaces(self, extractor: MarkdownExtractor) -> Set[Tuple[str, str]]:
        interfaces: Set[Tuple[str, str]] = set()
        table = extractor.table_after_heading(r"§13\s+接口清单")
        if not table or len(table) < 2:
            return interfaces
        header = [c.strip() for c in table[0]]
        method_idx = self._idx(header, ["方法", "HTTP 方法"])
        path_idx = self._idx(header, ["路径", "URL", "接口路径"])
        if method_idx is None or path_idx is None:
            return interfaces
        for row in table[1:]:
            if len(row) <= max(method_idx, path_idx):
                continue
            if re.match(r"^:?-+:?$", row[0]):
                continue
            method = row[method_idx].strip().strip("`\"'")
            path = row[path_idx].strip().strip("`\"'")
            if path:
                interfaces.add((method, path))
        return interfaces

    @staticmethod
    def _idx(header: List[str], candidates: List[str]) -> Optional[int]:
        for c in candidates:
            if c in header:
                return header.index(c)
        return None


class TableFieldInterfaceRefRule(Rule):
    """技术方案: 检查 §3 数据模型中的表字段是否在 §4 接口设计中被引用"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        # 1. 从 §3 的所有表格中提取字段名
        table_fields: List[str] = []
        tables = extractor.all_tables_after_heading(r"§3\s+数据模型")
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            field_idx = None
            for cand in ["字段名", "参数名", "名称", "字段"]:
                if cand in header:
                    field_idx = header.index(cand)
                    break
            if field_idx is None:
                field_idx = 0
            for row in table[1:]:
                if len(row) <= field_idx:
                    continue
                field = row[field_idx].strip()
                if field and not re.match(r"^:?-+:?$", field):
                    table_fields.append(field)

        if not table_fields:
            return []

        # 2. 获取 §4 的文本
        sec4_text = extractor.section_text(r"§4\s+接口设计")
        if not sec4_text:
            return []

        # 3. 检查每个字段是否在 §4 中出现
        issues = []
        for field in table_fields:
            pattern = r"\b" + re.escape(field) + r"\b"
            if not re.search(pattern, sec4_text):
                issues.append(Issue(
                    check_id=self.check_id,
                    severity="warning",
                    location="数据-接口映射",
                    message=f"§3 表字段 {field} 在 §4 接口设计中未出现"
                ))
        return issues


class ExceptionInterfaceRefRule(Rule):
    """技术方案: 检查 §7 异常处理中的错误码是否在 §4 接口设计中有对应"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)

        sec7_text = extractor.section_text(r"§7\s+异常处理")
        sec4_text = extractor.section_text(r"§4\s+接口设计")
        if not sec7_text or not sec4_text:
            return []

        err_pattern = r"\b(ERR-[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+)\b"
        sec7_errors = set(re.findall(err_pattern, sec7_text))
        sec4_errors = set(re.findall(err_pattern, sec4_text))

        issues = []
        for err in sorted(sec7_errors - sec4_errors):
            issues.append(Issue(
                check_id=self.check_id,
                severity="warning",
                location="异常-接口映射",
                message=f"§7 异常处理中的错误码 {err} 在 §4 接口设计中未出现"
            ))
        return issues


class TechAuditFieldRule(Rule):
    """技术方案: 检查 §3 每张数据模型表是否包含审计字段"""

    def __init__(self, check_id: str, audit_fields: List[str]):
        self.check_id = check_id
        self.audit_fields = audit_fields

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§3\s+数据模型")
        issues = []
        for idx, table in enumerate(tables, 1):
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if re.match(r"^:?-+:?$", header[0]):
                continue
            # 找到字段列
            field_col = None
            for i, h in enumerate(header):
                if h in ("字段", "字段名"):
                    field_col = i
                    break
            if field_col is None:
                continue
            # 提取该表所有字段名
            fields = []
            for row in table[1:]:
                if len(row) > field_col:
                    val = row[field_col].strip()
                    if val and not re.match(r"^:?-+:?$", val):
                        fields.append(val)
            # 检查是否有审计字段
            has_audit = any(any(audit in f for audit in self.audit_fields) for f in fields)
            if not has_audit:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location=f"§3 数据模型表 #{idx}",
                    message="未检测到审计字段（如 created_at/updated_at/creator_id 等）"
                ))
        return issues


class TechInterfaceElementsRule(Rule):
    """技术方案: 检查接口定义是否包含指定要素"""

    def __init__(self, check_id: str, required_elements: List[str]):
        self.check_id = check_id
        self.required_elements = required_elements

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec4_text = extractor.section_text(r"§4\s+接口设计")
        # 简单检查：接口定义通常以反引号包裹的 HTTP 方法开头
        api_blocks = re.findall(r"`(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}:.\-]+)`([\s\S]*?)(?=```|$|`(?:GET|POST|PUT|DELETE|PATCH))", sec4_text)
        issues = []
        for method, path, block in api_blocks:
            for elem in self.required_elements:
                if elem not in block:
                    issues.append(Issue(
                        check_id=self.check_id, severity="warning",
                        location=f"接口 {method} {path}",
                        message=f"缺少要素: {elem}"
                    ))
        return issues


class TestCaseFeatureRefRule(Rule):
    """测试方案: 检查 §1 每个用例是否标注了功能点和验收标准编号"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§1\s+功能测试")
        issues = []
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            fp_idx = next((i for i, h in enumerate(header) if "功能点" in h), None)
            ac_idx = next((i for i, h in enumerate(header) if "验收标准" in h), None)
            for row in table[1:]:
                if not row or re.match(r"^:?-+:?$", row[0]):
                    continue
                row_id = row[0].strip() if row else "未知"
                if fp_idx is not None and fp_idx < len(row):
                    val = row[fp_idx].strip()
                    if not val or val in ("-", "—", "", "无"):
                        issues.append(Issue(
                            check_id=self.check_id, severity="warning",
                            location="功能测试用例",
                            message=f"用例 {row_id} 缺少功能点编号"
                        ))
                if ac_idx is not None and ac_idx < len(row):
                    val = row[ac_idx].strip()
                    if not val or val in ("-", "—", "", "无"):
                        issues.append(Issue(
                            check_id=self.check_id, severity="warning",
                            location="功能测试用例",
                            message=f"用例 {row_id} 缺少验收标准编号"
                        ))
        return issues


class TestExceptionCoverageRule(Rule):
    """测试方案: 检查 §2 异常测试是否覆盖指定的异常类型"""

    def __init__(self, check_id: str, exception_types: List[str]):
        self.check_id = check_id
        self.exception_types = exception_types

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec2_text = extractor.section_text(r"§2\s+异常测试")
        if not sec2_text:
            return []
        issues = []
        for exc_type in self.exception_types:
            if exc_type not in sec2_text:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="异常测试覆盖",
                    message=f"未覆盖异常类型: {exc_type}"
                ))
        return issues


class TestCaseFormatRule(Rule):
    """测试: 检查用例表格是否包含指定列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        issues = []
        for idx, table in enumerate(data.tables, 1):
            if not table or not table[0]:
                continue
            header = [c.strip() for c in table[0]]
            # 识别测试用例表：包含"前置条件"或"测试步骤"
            if any("前置条件" in h or "测试步骤" in h for h in header):
                for col in self.required_cols:
                    if col not in header:
                        issues.append(Issue(
                            check_id=self.check_id, severity="blocking",
                            location=f"测试用例表 #{idx}",
                            message=f"缺少必填列: {col}"
                        ))
        return issues


# ── 第一批补充规则：表格列完整性 ──

class DataModelTableColumnsRule(Rule):
    """PRD: 检查 §5 数据模型表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§5\s+数据模型")
        issues = []
        for idx, table in enumerate(tables, 1):
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if re.match(r"^:?-+:?$", header[0]):
                continue
            for col in self.required_cols:
                if col not in header:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location=f"§5 数据模型表 #{idx}",
                        message=f"缺少必填列: {col}"
                    ))
        return issues


class ErrorCodeTableColumnsRule(Rule):
    """PRD: 检查 §7 错误码表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(r"§7\s+错误处理")
        if not table or len(table) < 2:
            return []
        header = [c.strip() for c in table[0]]
        issues = []
        for col in self.required_cols:
            if col not in header:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="§7 错误处理表头",
                    message=f"缺少必填列: {col}"
                ))
        return issues


class ExceptionTableColumnsRule(Rule):
    """技术方案: 检查 §7 异常处理表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§7\s+异常处理")
        issues = []
        for idx, table in enumerate(tables, 1):
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if re.match(r"^:?-+:?$", header[0]):
                continue
            for col in self.required_cols:
                if col not in header:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location=f"§7 异常处理表 #{idx}",
                        message=f"缺少必填列: {col}"
                    ))
        return issues


class InterfaceInventoryColumnsRule(Rule):
    """技术方案: 检查 §13 接口清单表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(r"§13\s+接口清单")
        if not table or len(table) < 2:
            return [Issue(
                check_id=self.check_id, severity="blocking",
                location="§13 接口清单",
                message="未找到接口清单表格"
            )]
        header = [c.strip() for c in table[0]]
        issues = []
        for col in self.required_cols:
            if col not in header:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="§13 接口清单表头",
                    message=f"缺少必填列: {col}"
                ))
        return issues


class InterfaceFeatureRefRule(Rule):
    """技术方案: 检查 §4 每个接口是否标注对应 PRD 功能点"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec4_text = extractor.section_text(r"§4\s+接口设计")
        # 提取接口定义区块
        api_blocks = re.findall(r"`(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}:.\-]+)`([\s\S]*?)(?=```|$|`(?:GET|POST|PUT|DELETE|PATCH))", sec4_text)
        issues = []
        for method, path, block in api_blocks:
            # 检查区块中是否包含功能编号格式的引用
            if not re.search(r"\b[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z][A-Za-z0-9_]*)*-\d+\b", block):
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location=f"接口 {method} {path}",
                    message="接口定义中未标注对应的功能点编号"
                ))
        return issues


class PerfTestColumnsRule(Rule):
    """测试: 检查 §3 性能测试表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        tables = extractor.all_tables_after_heading(r"§3\s+性能测试")
        issues = []
        for idx, table in enumerate(tables, 1):
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if re.match(r"^:?-+:?$", header[0]):
                continue
            for col in self.required_cols:
                if col not in header:
                    issues.append(Issue(
                        check_id=self.check_id, severity="blocking",
                        location=f"§3 性能测试表 #{idx}",
                        message=f"缺少必填列: {col}"
                    ))
        return issues


class CoverageReportColumnsRule(Rule):
    """测试: 检查 §6 覆盖检查报告表格是否包含必填列"""

    def __init__(self, check_id: str, required_cols: List[str]):
        self.check_id = check_id
        self.required_cols = required_cols

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        table = extractor.table_after_heading(r"§6\s+覆盖检查报告")
        if not table or len(table) < 2:
            return []
        header = [c.strip() for c in table[0]]
        issues = []
        for col in self.required_cols:
            if col not in header:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="§6 覆盖检查报告表头",
                    message=f"缺少必填列: {col}"
                ))
        return issues


class AdmissionCriteriaRule(Rule):
    """测试: 检查 §7 准入条件是否包含关键项"""

    def __init__(self, check_id: str, required_items: List[str]):
        self.check_id = check_id
        self.required_items = required_items

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec7_text = extractor.section_text(r"§7\s+回归测试策略")
        if not sec7_text:
            return []
        issues = []
        for item in self.required_items:
            if item not in sec7_text:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="§7 回归测试策略",
                    message=f"准入条件缺少: {item}"
                ))
        return issues


# ── 第二批补充规则：L2 相邻产物间 ──

class PRDCoverageConsistencyRule(Rule):
    """PRD: 检查 §1 声明的覆盖功能点列表与 §3 实际功能点是否一致"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        # 从 §1 文档信息中提取"覆盖功能点"列表
        # 匹配格式: **覆盖功能点**：TICKET-001, TICKET-002
        sec1_text = MarkdownExtractor(data.raw_text).section_text(r"§1\s+文档信息")
        coverage_match = re.search(r"覆盖功能点[：:]\s*([A-Za-z0-9_\-,\s]+)", sec1_text)
        if not coverage_match:
            return []
        covered_ids = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z][A-Za-z0-9_]*)*-\d+", coverage_match.group(1)))

        # 从 §3 表格第一列提取实际功能点
        extractor = MarkdownExtractor(data.raw_text)
        sec3_table = extractor.table_after_heading(r"§3\s+功能需求")
        actual_ids = set()
        if sec3_table and len(sec3_table) > 1:
            for row in sec3_table[1:]:
                if row and not re.match(r"^:?-+:?$", row[0]):
                    actual_ids.add(row[0].strip())

        issues = []
        missing = covered_ids - actual_ids
        extra = actual_ids - covered_ids
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§1 覆盖功能点",
                message=f"§1 声明但未在 §3 中找到的功能点: {', '.join(sorted(missing))}"
            ))
        if extra:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§3 功能需求",
                message=f"§3 存在但 §1 未声明的功能点: {', '.join(sorted(extra))}"
            ))
        return issues


class VersionConsistencyRule(Rule):
    """通用: 检查当前产物版本号与上游文档版本号是否一致"""

    def __init__(self, check_id: str, upstream_type: str = "upstream"):
        self.check_id = check_id
        self.upstream_type = upstream_type

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 提取当前产物版本号
        current_version = self._extract_version(data.raw_text)
        if not current_version:
            return []
        issues = []
        for path, up_data in ctx.upstream_docs.items():
            upstream_version = self._extract_version(up_data.raw_text)
            if upstream_version and upstream_version != current_version:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="版本号",
                    message=f"版本号不一致: 当前 {current_version}, 上游 {Path(path).name} 为 {upstream_version}"
                ))
        return issues

    @staticmethod
    def _extract_version(text: str) -> Optional[str]:
        m = re.search(r"版本号[：:]\s*(v?\d+\.\d+(?:\.\d+)?)", text)
        if m:
            return m.group(1)
        # 回退：从标题中提取 v{数字}
        m = re.search(r"-v(\d+\.\d+)", text)
        return f"v{m.group(1)}" if m else None


class UpstreamIdExistenceRule(Rule):
    """通用: 检查当前产物引用的 ID 在上游文档中是否存在"""

    def __init__(self, check_id: str, id_pattern: str, location_desc: str):
        self.check_id = check_id
        self.id_pattern = id_pattern
        self.location_desc = location_desc

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 收集当前产物中的引用 ID
        current_ids = set(re.findall(self.id_pattern, data.raw_text))
        if not current_ids:
            return []
        # 收集所有上游文档中的 ID
        upstream_ids: Set[str] = set()
        for up_data in ctx.upstream_docs.values():
            upstream_ids.update(up_data.ids)
            # 也尝试从 raw_text 中提取
            upstream_ids.update(re.findall(self.id_pattern, up_data.raw_text))

        issues = []
        missing = current_ids - upstream_ids
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location=self.location_desc,
                message=f"以下 ID 在上游文档中未找到: {', '.join(sorted(missing))}"
            ))
        return issues


class EnumConsistencyRule(Rule):
    """技术方案: 检查 §3 枚举值与上游 PRD §5/§6 是否一致"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 从技术方案 §3 提取枚举值（通常出现在"取值"或"枚举"描述中）
        extractor = MarkdownExtractor(data.raw_text)
        sec3_text = extractor.section_text(r"§3\s+数据模型")
        tech_enums = self._extract_enums(sec3_text)

        # 从上游 PRD 提取枚举值
        prd_enums: Dict[str, Set[str]] = {}
        for up_data in ctx.upstream_docs.values():
            prd_text = MarkdownExtractor(up_data.raw_text).section_text(r"§5\s+数据模型")
            if not prd_text:
                prd_text = MarkdownExtractor(up_data.raw_text).section_text(r"§6\s+业务规则")
            if prd_text:
                prd_enums.update(self._extract_enums(prd_text))

        issues = []
        for field, tech_vals in tech_enums.items():
            if field in prd_enums:
                missing = tech_vals - prd_enums[field]
                extra = prd_enums[field] - tech_vals
                if missing or extra:
                    issues.append(Issue(
                        check_id=self.check_id, severity="warning",
                        location=f"枚举值 {field}",
                        message=f"枚举值不一致: 技术方案={sorted(tech_vals)}, PRD={sorted(prd_enums[field])}"
                    ))
        return issues

    @staticmethod
    def _extract_enums(text: str) -> Dict[str, Set[str]]:
        """从文本中提取枚举值定义。格式如：取值：A / B / C"""
        enums: Dict[str, Set[str]] = {}
        # 匹配"取值：VALUE1 / VALUE2 / VALUE3"或"枚举：A, B, C"
        for m in re.finditer(r"(?:取值|枚举)[：:]\s*([^\n]+)", text):
            vals = set(v.strip() for v in re.split(r"[,，/、]", m.group(1)) if v.strip())
            # 尝试找到前面的字段名（简单回退：取最近一行的字段名）
            field = "unknown"
            lines_before = text[:m.start()].splitlines()
            for line in reversed(lines_before):
                cm = re.search(r"\|\s*([^|]+)\s*\|", line)
                if cm:
                    field = cm.group(1).strip()
                    break
            if vals:
                enums[field] = vals
        return enums


# ── 第三批补充规则：Tech/Test 跨产物 + Interaction 单产物 ──

class TechFieldToApiRefRule(Rule):
    """技术方案: 检查 §3 数据模型字段在 §4 接口请求/响应参数中有对应"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        # 从 §3 提取所有字段名
        tables = extractor.all_tables_after_heading(r"§3\s+数据模型")
        fields: Set[str] = set()
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [c.strip() for c in table[0]]
            if "字段" in header:
                col_idx = header.index("字段")
                for row in table[1:]:
                    if len(row) > col_idx:
                        val = row[col_idx].strip()
                        if val and not re.match(r"^:?-+:?$", val):
                            fields.add(val)

        # 从 §4 提取所有参数名（在反引号中或表格中）
        sec4_text = extractor.section_text(r"§4\s+接口设计")
        api_params = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", sec4_text))
        # 也提取表格中的字段名
        for table in extractor.all_tables_after_heading(r"§4\s+接口设计"):
            if table and table[0]:
                header = [c.strip() for c in table[0]]
                if "参数名" in header or "字段" in header:
                    col_idx = header.index("参数名") if "参数名" in header else header.index("字段")
                    for row in table[1:]:
                        if len(row) > col_idx:
                            val = row[col_idx].strip()
                            if val and not re.match(r"^:?-+:?$", val):
                                api_params.add(val)

        issues = []
        missing = fields - api_params
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§4 接口设计",
                message=f"以下数据模型字段在接口参数中未找到对应: {', '.join(sorted(missing)[:10])}"
            ))
        return issues


class TestCoverageVerificationRule(Rule):
    """测试: 检查 §6 中标记为'已覆盖'的验收标准在 §1/§2 中有对应用例"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        # 从 §6 提取已覆盖的验收标准编号
        sec6_table = extractor.table_after_heading(r"§6\s+覆盖检查报告")
        covered_ac: Set[str] = set()
        if sec6_table and len(sec6_table) > 1:
            header = [c.strip() for c in sec6_table[0]]
            ac_col = header.index("验收标准编号") if "验收标准编号" in header else 0
            status_col = header.index("状态") if "状态" in header else -1
            for row in sec6_table[1:]:
                if len(row) > max(ac_col, status_col):
                    status = row[status_col].strip() if status_col >= 0 else ""
                    if "已覆盖" in status:
                        covered_ac.add(row[ac_col].strip())

        # 从 §1/§2 文本中提取所有引用的验收标准编号
        all_cases_text = extractor.section_text(r"§1\s+功能测试用例") + "\n" + extractor.section_text(r"§2\s+异常测试用例")
        issues = []
        for ac_id in covered_ac:
            if ac_id not in all_cases_text:
                issues.append(Issue(
                    check_id=self.check_id, severity="blocking",
                    location="§6 覆盖检查报告",
                    message=f"验收标准 {ac_id} 标记为已覆盖，但在 §1/§2 中未找到对应用例"
                ))
        return issues


class TestExceptionCompletenessRule(Rule):
    """测试: 检查 §2 异常场景是否覆盖上游技术方案 §7 所有异常"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 从当前测试 §2 提取异常场景/错误码
        extractor = MarkdownExtractor(data.raw_text)
        test_sec2_text = extractor.section_text(r"§2\s+异常测试用例")
        test_exceptions = set(re.findall(r"ERR-[A-Z]+-\d+", test_sec2_text))

        # 从上游 Tech §7 提取异常/错误码
        tech_exceptions: Set[str] = set()
        for up_data in ctx.upstream_docs.values():
            tech_text = MarkdownExtractor(up_data.raw_text).section_text(r"§7\s+异常处理")
            tech_exceptions.update(re.findall(r"ERR-[A-Z]+-\d+", tech_text))

        issues = []
        missing = tech_exceptions - test_exceptions
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§2 异常测试用例",
                message=f"以下技术方案中的异常/错误码未在测试 §2 中覆盖: {', '.join(sorted(missing))}"
            ))
        return issues


class TestSecurityCompletenessRule(Rule):
    """测试: 检查 §4 安全测试是否覆盖上游技术方案 §10 所有安全措施"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 从当前测试 §4 提取安全测试项
        extractor = MarkdownExtractor(data.raw_text)
        test_sec4_text = extractor.section_text(r"§4\s+安全测试")
        # 简单提取表格第一列作为测试项
        test_items: Set[str] = set()
        for table in extractor.all_tables_after_heading(r"§4\s+安全测试"):
            if table and len(table) > 1:
                for row in table[1:]:
                    if row and row[0].strip():
                        test_items.add(row[0].strip())

        # 从上游 Tech §10 提取安全措施
        tech_items: Set[str] = set()
        for up_data in ctx.upstream_docs.values():
            tech_text = MarkdownExtractor(up_data.raw_text).section_text(r"§10\s+安全设计")
            for table in MarkdownExtractor(up_data.raw_text).all_tables_after_heading(r"§10\s+安全设计"):
                if table and len(table) > 1:
                    for row in table[1:]:
                        if row and row[0].strip():
                            tech_items.add(row[0].strip())

        issues = []
        missing = tech_items - test_items
        if missing:
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§4 安全测试",
                message=f"以下技术方案安全措施未在安全测试中覆盖: {', '.join(sorted(missing)[:10])}"
            ))
        return issues


class InteractionJumpTargetRule(Rule):
    """交互设计: 检查页面跳转目标是否在本产物范围内或正确引用外部"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        # 提取本文档中所有页面编号
        local_pages = set()
        for level, text in data.sections:
            m = re.search(r"[A-Z]+(?:-[A-Z]+)*-\d+", text)
            if m:
                local_pages.add(m.group(0))

        # 从全文提取跳转目标引用
        jump_patterns = [
            r"跳转到\s*([^\s，。]+)",
            r"返回\s*([^\s，。]+)",
            r"进入\s*([^\s，。]+)",
            r"href\s*=\s*['\"]([^'\"]+)['\"]",
        ]
        issues = []
        for pattern in jump_patterns:
            for target in re.findall(pattern, data.raw_text):
                target = target.strip()
                # 如果目标是页面编号格式，检查是否在本地
                if re.match(r"[A-Z]+(?:-[A-Z]+)*-\d+", target) and target not in local_pages:
                    issues.append(Issue(
                        check_id=self.check_id, severity="warning",
                        location="页面跳转",
                        message=f"跳转目标 '{target}' 不在本产物页面列表中，请确认是否为外部引用"
                    ))
        return issues


class TechPerformanceAlignmentRule(Rule):
    """技术方案: 检查 §8 性能目标是否与上游 PRD §4 非功能需求一致"""

    def __init__(self, check_id: str):
        self.check_id = check_id

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template or not ctx.upstream_docs:
            return []
        # 从上游 PRD §4 提取性能指标关键词
        prd_metrics: Set[str] = set()
        for up_data in ctx.upstream_docs.values():
            prd_text = MarkdownExtractor(up_data.raw_text).section_text(r"§4\s+非功能需求")
            # 提取包含数字的绩效指标行
            for line in prd_text.splitlines():
                if re.search(r"\d+\s*(ms|s|秒|QPS|TPS|RPS|并发)", line):
                    # 取前 20 字符作为指标标识
                    prd_metrics.add(line.strip()[:30])

        # 从当前 Tech §8 提取性能目标
        extractor = MarkdownExtractor(data.raw_text)
        tech_text = extractor.section_text(r"§8\s+性能与扩展性")
        issues = []
        for metric in prd_metrics:
            # 简化匹配：检查 PRD 指标关键词是否在 Tech §8 中出现
            keyword = re.sub(r"\d+\s*(ms|s|秒|QPS|TPS|RPS|并发).*", r"\1", metric)
            if keyword and keyword not in tech_text:
                issues.append(Issue(
                    check_id=self.check_id, severity="warning",
                    location="§8 性能与扩展性",
                    message=f"PRD §4 中的性能指标未在技术方案 §8 中找到对应目标"
                ))
        return issues


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 各产物类型的规则集
# ═══════════════════════════════════════════════════════════════════════════════

PRD_RULES: List[Rule] = [
    SectionExistsRule("P-A1", [
        "背景与目标", "用户与场景", "功能需求", "非功能需求",
        "数据模型", "业务规则", "错误处理", "验收标准", "依赖与范围", "附件",
    ]),
    FeatureTableColumnsRule("P-A7", ["功能编号", "故事编号", "功能名称", "优先级", "交互方式", "技术实现单元", "业务规则", "验收标准"]),
    DataModelTableColumnsRule("P-A8", ["字段", "类型", "约束", "说明"]),
    ErrorCodeTableColumnsRule("P-A9", ["错误码", "触发场景", "前端提示"]),
    IdFormatConsistencyRule("P-A5"),
    IdDuplicateRule("P-A6"),
    IdContinuityRule("P-A6"),
    ReverseFeatureRefRule("P-A8", r"§6\s+业务规则", "§6 业务规则"),
    ReverseFeatureRefRule("P-A10", r"§7\s+错误处理", "§7 错误处理"),
    InternalRefRule("P-A13"),
    AcceptanceFeatureRefRule("P-A12"),
    P0AcceptanceRule("P-A14"),
    TableFormatRule("P-A15"),
    BrokenInternalLinkRule("P-A16"),
    CrossDocTerminologyRule("P-B2"),
    PRDCoverageConsistencyRule("P-B3"),
    VersionConsistencyRule("P-B4"),
    UpstreamRefRule("P-B5"),
]

INTERACTION_RULES: List[Rule] = [
    PageStructureRule("I-A2", [
        "页面结构", "组件交互", "状态机", "页面流程", "异常处理", "与 PRD 对应",
    ]),
    SVGExistRule("I-A3"),
    StateMatrixRule("I-A5", expected_cols=6),
    StateMatrixRule("I-A6", expected_cols=7, col_name="力学约束"),
    PageFlowColumnsRule("I-A8", ["前置条件", "用户操作", "系统响应", "反馈方式", "后置状态"]),
    ExceptionColumnsRule("I-A9", ["异常场景", "触发条件", "系统响应", "用户感知", "恢复路径"]),
    PagePrefixConsistencyRule("I-B1"),
    UpstreamIdExistenceRule("I-B2", r"[A-Z]+(?:-[A-Z]+)*-\d+", "页面编号"),
    VersionConsistencyRule("I-B3"),
    InteractionJumpTargetRule("I-B4"),
    TableFormatRule("I-A12"),
    UpstreamRefRule("I-B6"),
]

UI_RULES: List[Rule] = [
    RegexMatchRule("U-A1", r"<!DOCTYPE\s+html", "", severity="blocking",
                   message="缺少 <!DOCTYPE html>"),
    RegexMatchRule("U-A2", r"<!--\s*upstream:", "", severity="blocking",
                   message="头部缺少 upstream 注释声明"),
    RegexMatchRule("U-A3", r"\bfetch\b|\bXMLHttpRequest\b|\.ajax\b|axios\b", "",
                   should_match=False, severity="blocking",
                   message="包含数据请求逻辑，UI 原型应使用静态假数据"),
    RegexMatchRule("U-A5", r"var\(--", "", severity="blocking",
                   message="未使用 CSS 变量（var(--*)）"),
    RegexMatchRule("U-A6", r"#[0-9a-fA-F]{3,8}\b|rgba?\s*\(", "", should_match=False,
                   severity="warning", message="发现硬编码色值，应使用 CSS 变量"),
    UIStateMapRule("U-A7"),
    UIClassConsistencyRule("U-A8"),
    StateStyleExistRule("U-B3", ["hover", "active", "focus", "disabled", "loading", "empty", "error", "success", "skeleton"]),
    PageCoverageRule("U-B1"),
    UpstreamIdExistenceRule("U-B2", r"page-[a-z0-9-]+", "section id"),
    VersionConsistencyRule("U-B3"),
    ResponsiveBreakpointRule("U-B5"),
    TableFormatRule("U-A12"),
    UpstreamRefRule("U-B7"),
]

TECH_RULES: List[Rule] = [
    SectionExistsRule("T-A1", [
        "技术决策", "依赖关系", "数据模型", "接口设计", "状态机设计",
        "核心流程", "异常处理", "性能与扩展性", "高可用设计", "安全设计",
        "监控与日志", "灰度与回滚", "接口清单", "风险评估",
    ]),
    TechAuditFieldRule("T-A2", ["created_at", "updated_at", "creator_id", "updater_id", "created_by", "updated_by"]),
    TechInterfaceElementsRule("T-A4", ["URL", "方法", "请求参数", "响应结构", "错误码", "版本号"]),
    TableColumnCompletenessRule("T-A3", ["字段", "类型", "约束", "索引", "对应 PRD 字段", "设计说明"]),
    InterfaceFeatureRefRule("T-A5"),
    ExceptionTableColumnsRule("T-A6", ["异常编号", "异常类型", "场景", "触发条件", "技术处理", "用户提示", "错误码"]),
    InterfaceInventoryColumnsRule("T-A7", ["序号", "接口名", "方法", "路径", "对应功能点", "权限", "版本"]),
    InterfaceInventoryMatchRule("T-A9"),
    TableFieldInterfaceRefRule("T-A10"),
    ExceptionInterfaceRefRule("T-A11"),
    TableFormatRule("T-A12"),
    BrokenInternalLinkRule("T-A13"),
    BidirectionalMappingRule("T-B1", forward_severity="warning", reverse_severity="warning"),
    CrossDocTerminologyRule("T-B2"),
    EnumConsistencyRule("T-B3"),
    UpstreamIdExistenceRule("T-B4", r"ERR-[A-Z]+-\d+", "错误码"),
    VersionConsistencyRule("T-B5"),
    TechFieldToApiRefRule("T-B6"),
    TechPerformanceAlignmentRule("T-B7"),
    UpstreamRefRule("T-B13"),
]

TEST_RULES: List[Rule] = [
    SectionExistsRule("S-A1", [
        "功能测试用例", "异常测试用例", "性能测试",
        "安全测试", "兼容性测试", "覆盖检查报告", "回归测试策略",
    ]),
    TestCaseFormatRule("S-A2", ["前置条件", "测试步骤", "预期结果"]),
    TestCaseFeatureRefRule("S-A3"),
    TestExceptionCoverageRule("S-A4", [
        "参数非法", "权限不足", "数据不存在", "网络异常", "并发冲突", "第三方故障",
    ]),
    PerfTestColumnsRule("S-A5", ["测试项", "性能目标", "测试场景", "测试数据量", "通过标准", "优先级"]),
    CoverageReportColumnsRule("S-A6", ["验收标准编号", "验收标准描述", "覆盖用例编号", "状态", "未覆盖原因"]),
    AdmissionCriteriaRule("S-A7", ["代码审查", "单元测试", "构建成功"]),
    InterfaceTestCoverageRule("S-B5"),
    UpstreamIdExistenceRule("S-B6", r"[A-Z]+(?:-[A-Z]+)*-\d+", "功能点/用例编号"),
    VersionConsistencyRule("S-B7"),
    TestCoverageVerificationRule("S-A8"),
    TestExceptionCompletenessRule("S-A9"),
    TestSecurityCompletenessRule("S-A10"),
    TableFormatRule("S-A11"),
    UpstreamRefRule("S-B10"),
]


RULE_SETS = {
    "prd": PRD_RULES,
    "interaction": INTERACTION_RULES,
    "ui": UI_RULES,
    "tech": TECH_RULES,
    "test": TEST_RULES,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 引擎层
# ═══════════════════════════════════════════════════════════════════════════════

class AuditEngine:
    """审计引擎：提取数据 → 加载规则 → 执行检查 → 汇总结果"""

    def __init__(self, doc_path: str, doc_type: str, upstream_paths: Optional[List[str]] = None):
        self.doc_path = Path(doc_path)
        self.doc_type = doc_type
        self.raw_text = self.doc_path.read_text(encoding="utf-8")
        self.data = self._extract()
        self.ctx = AuditContext(doc_path=self.doc_path, doc_type=doc_type)
        self._load_upstream(upstream_paths or [])

    def _extract(self) -> ExtractedData:
        if self.doc_path.suffix == ".html":
            return HTMLExtractor(self.raw_text).extract()
        return MarkdownExtractor(self.raw_text).extract()

    def _detect_template(self) -> bool:
        """检测是否为产物模板（包含示例说明，非实际产物）"""
        markers = ["填写示例", "不要机械套用", "常见陷阱", "产物模板"]
        return any(m in self.raw_text for m in markers)

    def _load_upstream(self, upstream_paths: List[str]):
        for up_path in upstream_paths:
            p = Path(up_path)
            if p.exists():
                text = p.read_text(encoding="utf-8")
                if p.suffix == ".html":
                    self.ctx.upstream_docs[str(p)] = HTMLExtractor(text).extract()
                else:
                    self.ctx.upstream_docs[str(p)] = MarkdownExtractor(text).extract()

    def run(self) -> dict:
        self.ctx.is_template = self._detect_template()
        rules = RULE_SETS.get(self.doc_type, [])
        issues: List[Issue] = []
        for rule in rules:
            issues.extend(rule.check(self.data, self.ctx))

        blocking = [i for i in issues if i.severity == "blocking"]
        return {
            "passed": len(blocking) == 0,
            "doc": str(self.doc_path),
            "mechanical_issues": [
                {"check_id": i.check_id, "severity": i.severity,
                 "location": i.location, "message": i.message}
                for i in issues
            ],
            "summary": {
                "blocking": len(blocking),
                "warning": len([i for i in issues if i.severity == "warning"]),
                "info": len([i for i in issues if i.severity == "info"]),
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 下游扫描
# ═══════════════════════════════════════════════════════════════════════════════

def scan_downstream(doc_path: Path, docs_dir: Path) -> List[dict]:
    downstream: List[dict] = []
    target_name = doc_path.stem

    for md_file in docs_dir.rglob("*.md"):
        if md_file.resolve() == doc_path.resolve():
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if "上游文档" in text:
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
                downstream.append({
                    "path": str(md_file.relative_to(docs_dir)),
                    "scope": scope_match.group(1).strip(),
                    "type": "markdown",
                })

    for html_file in docs_dir.rglob("*.html"):
        if html_file.resolve() == doc_path.resolve():
            continue
        try:
            text = html_file.read_text(encoding="utf-8")
        except Exception:
            continue
        upstream_comments = re.findall(r"<!--\s*upstream:([^>]+)-->", text, re.IGNORECASE)
        for comment in upstream_comments:
            if target_name in comment:
                scope_match = re.search(
                    rf"{re.escape(target_name)}(?:\.md)?\s*,?\s*([^,\n]+)?",
                    comment,
                )
                scope = scope_match.group(1).strip() if scope_match and scope_match.group(1) else "UI 设计"
                downstream.append({
                    "path": str(html_file.relative_to(docs_dir)),
                    "scope": scope,
                    "type": "html",
                })
                break
    return downstream


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="产物一致性审计规则引擎")
    parser.add_argument("doc_path", help="待审计产物路径")
    parser.add_argument("--type", required=True, choices=list(RULE_SETS.keys()), help="产物类型")
    parser.add_argument("--upstream", nargs="*", default=[], help="上游文档路径")
    parser.add_argument("--scan-downstream", metavar="DIR", default="", help="扫描下游引用")
    args = parser.parse_args()

    doc_path = Path(args.doc_path)
    if not doc_path.exists():
        print(json.dumps({"error": f"文件不存在: {doc_path}"}, ensure_ascii=False))
        sys.exit(1)

    if args.scan_downstream:
        docs_dir = Path(args.scan_downstream)
        if not docs_dir.is_dir():
            print(json.dumps({"error": f"目录不存在: {docs_dir}"}, ensure_ascii=False))
            sys.exit(1)
        downstream = scan_downstream(doc_path, docs_dir)
        print(json.dumps({
            "mode": "downstream_scan",
            "doc": str(doc_path),
            "downstream_count": len(downstream),
            "downstream": downstream,
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    engine = AuditEngine(str(doc_path), args.type, upstream_paths=args.upstream)
    result = engine.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
