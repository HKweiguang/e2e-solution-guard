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
        """提取匹配 header_pattern 的 heading 及其子章节文本（直到同级或更高级 heading）"""
        start_idx = -1
        level = 6
        for idx, n in enumerate(self.nodes):
            if n["type"] == "heading" and re.search(header_pattern, n["text"]):
                start_idx = idx
                level = n["level"]
                break
        if start_idx == -1:
            return ""

        parts: List[str] = []
        for n in self.nodes[start_idx + 1:]:
            if n["type"] == "heading" and n["level"] <= level:
                break
            if n["type"] == "table":
                for row in n["rows"]:
                    parts.append("| " + " | ".join(row) + " |")
            elif n["type"] == "code":
                parts.append(f"```{n['lang']}")
                parts.append(n["content"])
                parts.append("```")
            else:
                parts.append(n.get("text", ""))
        return "\n".join(parts)

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

    def ids_in_section(self, header_pattern: str, id_pattern: Optional[str] = None) -> Set[str]:
        """从指定章节中提取编号"""
        text = self.section_text(header_pattern)
        if not text:
            return set()
        if id_pattern:
            return set(re.findall(id_pattern, text))
        # 默认模式
        return set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z][A-Za-z0-9_]*)*-\d+\b", text))


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


class TechAuditFieldRule(Rule):
    """技术方案: 检查数据模型中是否包含审计字段"""

    def __init__(self, check_id: str, audit_fields: List[str]):
        self.check_id = check_id
        self.audit_fields = audit_fields

    def check(self, data: ExtractedData, ctx: AuditContext) -> List[Issue]:
        if ctx.is_template:
            return []
        extractor = MarkdownExtractor(data.raw_text)
        sec3_text = extractor.section_text(r"§3\s+数据模型")
        if not sec3_text:
            return []
        issues = []
        if not any(field in sec3_text for field in self.audit_fields):
            issues.append(Issue(
                check_id=self.check_id, severity="warning",
                location="§3 数据模型",
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


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 各产物类型的规则集
# ═══════════════════════════════════════════════════════════════════════════════

PRD_RULES: List[Rule] = [
    SectionExistsRule("P-A1", [
        "背景与目标", "用户与场景", "功能需求", "非功能需求",
        "数据模型", "业务规则", "错误处理", "验收标准", "依赖与范围", "附件",
    ]),
    FeatureTableColumnsRule("P-A7", ["功能编号", "故事编号", "功能名称", "优先级", "交互方式"]),
    IdDuplicateRule("P-A6"),
    IdContinuityRule("P-A6"),
    InternalRefRule("P-A13"),
    AcceptanceFeatureRefRule("P-A12"),
    P0AcceptanceRule("P-A14"),
    TableFormatRule("P-A15"),
    UpstreamRefRule("P-B4"),
]

INTERACTION_RULES: List[Rule] = [
    SVGExistRule("I-A3"),
    StateMatrixRule("I-A5", expected_cols=6),
    StateMatrixRule("I-A6", expected_cols=7, col_name="力学约束"),
    PageFlowColumnsRule("I-A8", ["前置条件", "用户操作", "系统响应", "反馈方式", "后置状态"]),
    ExceptionColumnsRule("I-A9", ["异常场景", "触发条件", "系统响应", "用户感知", "恢复路径"]),
    TableFormatRule("I-A12"),
    UpstreamRefRule("I-B5"),
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
    TableFormatRule("U-A12"),
    UpstreamRefRule("U-B6"),
]

TECH_RULES: List[Rule] = [
    SectionExistsRule("T-A1", [
        "技术决策", "依赖关系", "数据模型", "接口设计", "状态机设计",
        "核心流程", "异常处理", "性能与扩展性", "高可用设计", "安全设计",
        "监控与日志", "灰度与回滚", "接口清单", "风险评估",
    ]),
    TechAuditFieldRule("T-A2", ["created_at", "updated_at", "creator_id", "updater_id", "created_by", "updated_by"]),
    TechInterfaceElementsRule("T-A4", ["URL", "方法", "请求参数", "响应结构", "错误码"]),
    TableFormatRule("T-A12"),
    UpstreamRefRule("T-B12"),
]

TEST_RULES: List[Rule] = [
    SectionExistsRule("S-A1", [
        "功能测试用例", "异常测试用例", "性能测试",
        "安全测试", "兼容性测试", "覆盖检查报告", "回归测试策略",
    ]),
    TestCaseFormatRule("S-A2", ["前置条件", "测试步骤", "预期结果"]),
    TableFormatRule("S-A11"),
    UpstreamRefRule("S-B9"),
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
