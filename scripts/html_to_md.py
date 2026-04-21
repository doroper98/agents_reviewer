"""Convert an existing HTML analysis report to Markdown.

Usage:
    python3 scripts/html_to_md.py reports/analysis_20260422_080834.html
    python3 scripts/html_to_md.py reports/analysis_20260422_080834.html --upload

The --upload flag also deploys to Cloudflare Pages afterwards.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from html.parser import HTMLParser


class ReportParser(HTMLParser):
    """Parse the analysis report HTML and extract structured content."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.category = ""
        self.generated_at = ""
        self.executive_summary = ""
        self.key_summary_items: list[str] = []
        self.sections: list[dict] = []
        self.sources: list[str] = []

        self._in_hero_h1 = False
        self._in_hero_sub = False
        self._in_hero_tags = False
        self._hero_tag_buf: list[str] = []

        self._in_key_summary = False
        self._in_key_summary_li = False
        self._key_li_buf: list[str] = []

        self._section_stack: list[dict] = []
        self._current_section: dict | None = None
        self._in_section_label = False
        self._in_section_title = False
        self._in_section_desc = False
        self._text_buf: list[str] = []

        self._capturing_block = False
        self._block_buf: list[str] = []
        self._block_type: str | None = None
        self._block_attrs: dict = {}

        self._skip_depth = 0
        self._tag_depth_sections: list[int] = []

    def _attr_get(self, attrs: list[tuple], key: str) -> str:
        for k, v in attrs:
            if k == key:
                return v or ""
        return ""

    def _has_class(self, attrs: list[tuple], cls: str) -> bool:
        c = self._attr_get(attrs, "class")
        return cls in c.split()

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        cls = self._attr_get(attrs, "class")

        if tag in ("script", "style", "svg", "canvas"):
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        # Hero h1
        if tag == "h1" and not self.title:
            self._in_hero_h1 = True
            self._text_buf = []
            return

        # Hero subtitle
        if tag == "p" and "hero-sub" in cls and not self.executive_summary:
            self._in_hero_sub = True
            self._text_buf = []
            return

        # Hero tags (category, date)
        if tag == "div" and "hero-tags" in cls:
            self._in_hero_tags = True
            return
        if self._in_hero_tags and tag == "span":
            self._hero_tag_buf = []
            self._text_buf = []
            return

        # Key summary
        if tag == "div" and "key-summary" in cls:
            self._in_key_summary = True
            return
        if self._in_key_summary and tag == "li":
            self._in_key_summary_li = True
            self._text_buf = []
            return

        # Section detection
        if tag == "section":
            sec_id = self._attr_get(attrs, "id")
            if sec_id and sec_id.startswith("s"):
                new_sec = {
                    "id": sec_id,
                    "label": "",
                    "title": "",
                    "desc": "",
                    "blocks": [],
                }
                self._current_section = new_sec
                self.sections.append(new_sec)
                return

        if self._current_section is not None:
            if tag == "div" and "section-label" in cls:
                self._in_section_label = True
                self._text_buf = []
                return
            if tag in ("h2", "h3") and "section-title" in cls:
                self._in_section_title = True
                self._text_buf = []
                return
            if (tag == "p" or tag == "div") and "section-desc" in cls:
                self._in_section_desc = True
                self._text_buf = []
                return

            # Content blocks inside section
            if tag in ("div", "table", "p"):
                if not self._capturing_block:
                    self._capturing_block = True
                    self._block_buf = []
                    self._block_type = tag
                    self._block_attrs = dict(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "svg", "canvas"):
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        if self._in_hero_h1 and tag == "h1":
            self.title = "".join(self._text_buf).strip()
            self._in_hero_h1 = False
            return

        if self._in_hero_sub and tag == "p":
            self.executive_summary = "".join(self._text_buf).strip()
            self._in_hero_sub = False
            return

        if self._in_hero_tags:
            if tag == "span":
                text = "".join(self._text_buf).strip()
                self._hero_tag_buf.append(text)
                return
            if tag == "div":
                # Heuristic: first tag = category, last tag = generated timestamp
                if self._hero_tag_buf:
                    if len(self._hero_tag_buf) >= 1 and not self.category:
                        self.category = self._hero_tag_buf[0]
                    if len(self._hero_tag_buf) >= 2:
                        self.generated_at = self._hero_tag_buf[-1]
                    elif len(self._hero_tag_buf) == 1:
                        self.generated_at = self._hero_tag_buf[0]
                self._in_hero_tags = False
                return

        if self._in_key_summary_li and tag == "li":
            item = "".join(self._text_buf).strip()
            if item:
                self.key_summary_items.append(item)
            self._in_key_summary_li = False
            return
        if self._in_key_summary and tag == "div":
            # Only end key summary when outer div closes — heuristic by class
            pass

        if self._current_section is not None:
            if self._in_section_label and tag == "div":
                self._current_section["label"] = "".join(self._text_buf).strip()
                self._in_section_label = False
                return
            if self._in_section_title and tag in ("h2", "h3"):
                self._current_section["title"] = "".join(self._text_buf).strip()
                self._in_section_title = False
                return
            if self._in_section_desc and tag in ("p", "div"):
                self._current_section["desc"] = "".join(self._text_buf).strip()
                self._in_section_desc = False
                return

            if tag == "section":
                self._current_section = None
                return

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if (
            self._in_hero_h1
            or self._in_hero_sub
            or self._in_hero_tags
            or self._in_key_summary_li
            or self._in_section_label
            or self._in_section_title
            or self._in_section_desc
        ):
            self._text_buf.append(data)
            return

        # Collect section body text
        if self._current_section is not None:
            text = data.strip()
            if text:
                self._current_section["blocks"].append(text)


def extract_text_from_html(html_content: str) -> dict:
    """Parse HTML and return structured content dict."""
    parser = ReportParser()
    parser.feed(html_content)
    return {
        "title": parser.title,
        "category": parser.category,
        "generated_at": parser.generated_at,
        "executive_summary": parser.executive_summary,
        "key_summary_items": parser.key_summary_items,
        "sections": parser.sections,
    }


def build_markdown(data: dict) -> str:
    """Convert parsed data into clean markdown."""
    lines: list[str] = []

    lines.append(f"# {data['title'] or 'Analysis'}\n")
    if data["category"]:
        lines.append(f"**Category:** {data['category']}  ")
    if data["generated_at"]:
        lines.append(f"**Generated:** {data['generated_at']}  \n")

    if data["executive_summary"]:
        lines.append("## Executive Summary\n")
        lines.append(f"{data['executive_summary']}\n")

    if data["key_summary_items"]:
        lines.append("## Key Points\n")
        for i, item in enumerate(data["key_summary_items"], 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    for sec in data["sections"]:
        label = sec.get("label", "").strip()
        title = sec.get("title", "").strip()
        if label and title:
            lines.append(f"## {label} — {title}\n")
        elif title:
            lines.append(f"## {title}\n")
        else:
            continue

        if sec.get("desc"):
            lines.append(f"_{sec['desc']}_\n")

        # Flatten block text. Remove duplicates and join paragraphs.
        seen: set[str] = set()
        body_parts: list[str] = []
        for b in sec.get("blocks", []):
            b = b.strip()
            if not b or b in seen or len(b) < 2:
                continue
            seen.add(b)
            body_parts.append(b)

        if body_parts:
            # Re-join with appropriate spacing
            current_para: list[str] = []
            for part in body_parts:
                current_para.append(part)
                if len(" ".join(current_para)) > 80:
                    lines.append(" ".join(current_para))
                    lines.append("")
                    current_para = []
            if current_para:
                lines.append(" ".join(current_para))
                lines.append("")

    lines.append("---")
    lines.append("Generated by Event Analysis Team (converted from HTML)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert analysis HTML report to Markdown")
    ap.add_argument("html_path", help="Path to the HTML report file")
    ap.add_argument("--upload", action="store_true", help="Also upload to Cloudflare Pages")
    ap.add_argument(
        "--project-name",
        default="analysis-reports",
        help="Cloudflare Pages project name",
    )
    ap.add_argument("--branch", default="main", help="Cloudflare Pages branch")
    args = ap.parse_args()

    if not os.path.isfile(args.html_path):
        print(f"Error: file not found: {args.html_path}", file=sys.stderr)
        return 1

    with open(args.html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    data = extract_text_from_html(html_content)
    md = build_markdown(data)

    md_path = args.html_path.replace(".html", ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✓ Markdown written: {md_path}")
    print(f"  Title: {data['title']}")
    print(f"  Sections: {len(data['sections'])}")
    print(f"  Size: {len(md)} bytes")

    if args.upload:
        output_dir = os.path.dirname(args.html_path) or "."
        # Ensure _headers file
        headers_path = os.path.join(output_dir, "_headers")
        headers_content = (
            "/*.md\n"
            "  Content-Type: text/plain; charset=utf-8\n"
            "  Access-Control-Allow-Origin: *\n"
        )
        if not os.path.exists(headers_path):
            with open(headers_path, "w", encoding="utf-8") as f:
                f.write(headers_content)

        print(f"\nUploading to Cloudflare Pages (project: {args.project_name}, branch: {args.branch})...")
        result = subprocess.run(
            [
                "wrangler", "pages", "deploy", output_dir,
                "--project-name", args.project_name,
                "--branch", args.branch,
                "--commit-message", "deploy md conversion",
            ],
            capture_output=True, text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            return 1

        basename = os.path.basename(md_path)
        print(f"\n✓ Available at: https://{args.project_name}.pages.dev/{basename}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
