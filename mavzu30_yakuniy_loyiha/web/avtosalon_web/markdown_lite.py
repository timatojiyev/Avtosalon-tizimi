"""Juda kichik Markdown → HTML konvertor (tashqi kutubxonasiz, internetsiz ishlaydi).

Qo'llab-quvvatlanadi: sarlavhalar, paragraflar, ro'yxatlar (raqamli/belgili), jadvallar, ``` kod bloklari
(```mermaid — diagramma uchun alohida <div>), > iqtibos, --- chiziq, **qalin**, *kursiv*, `kod`, [havola](url).
Barcha matn avval HTML-escape qilinadi — XSS xavfi yo'q.
"""
from __future__ import annotations

import html
import re
from typing import Callable

_INLINE = [
    (re.compile(r"`([^`]+)`"), lambda m: f"<code>{m.group(1)}</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), lambda m: f"<strong>{m.group(1)}</strong>"),
    (re.compile(r"(?<![\w*])\*([^*\s][^*]*)\*(?!\w)"), lambda m: f"<em>{m.group(1)}</em>"),
]
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _inline(text: str, link: Callable[[str], str]) -> str:
    text = html.escape(text, quote=False)
    parts = re.split(r"(`[^`]+`)", text)            # kod ichida boshqa formatlash qo'llanmaydi
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{part[1:-1]}</code>")
            continue
        for rx, fn in _INLINE[1:]:
            part = rx.sub(fn, part)
        part = _LINK.sub(lambda m: f'<a href="{html.escape(link(m.group(2)))}">{m.group(1)}</a>', part)
        out.append(part)
    return "".join(out)


def render(md: str, link: Callable[[str], str] = lambda u: u) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            code = html.escape("\n".join(block))
            out.append(f'<div class="mermaid">{code}</div>' if lang == "mermaid" else f"<pre><code>{code}</code></pre>")
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        if m := re.match(r"^(#{1,4})\s+(.*)$", stripped):
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2), link)}</h{level}>")
            i += 1
            continue
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            th = "".join(f"<th>{_inline(c, link)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{_inline(c, link)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue
        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{'<br>'.join(_inline(q, link) for q in quote)}</blockquote>")
            continue
        if re.match(r"^([-*]|\d+\.)\s+", stripped):
            ordered = bool(re.match(r"^\d+\.", stripped))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    items[-1] += " " + lines[i].strip()
                    i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(it, link)}</li>" for it in items) + f"</{tag}>")
            continue
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|>|---|[-*]\s|\d+\.\s)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para), link)}</p>")
    return "\n".join(out)
