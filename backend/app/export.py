"""Export edited minutes as Markdown, Word (.docx) or PDF."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _attendees(m: dict) -> str:
    return ", ".join(a["name"] for a in m.get("attendees", [])) or "-"


def to_markdown(m: dict) -> str:
    lines = [f"# Minutes of Meeting: {m['title']}", ""]
    lines.append(f"**Date:** {m.get('datetime', '').replace('T', ' ')}")
    lines += [f"**Attendees:** {_attendees(m)}", ""]
    if m.get("agenda", "").strip():
        lines += ["## Agenda", m["agenda"].strip(), ""]
    lines.append("## Key Discussions")
    lines += [f"{i}. **{t['title']}**: {t['summary']}" for i, t in enumerate(m["topics"], 1)]
    lines += ["", "## Decisions"]
    lines += [f"{i}. {d['statement']}" for i, d in enumerate(m["decisions"], 1)]
    lines += ["", "## Action Items", "| Task | Owner | Deadline | Status |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {a['task']} | {a['owner']} | {a['due'] or '-'} | {a['status']} |"
        for a in m["actionItems"]
    ]
    return "\n".join(lines) + "\n"


def to_docx(m: dict) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(f"Minutes of Meeting: {m['title']}", level=0)
    doc.add_paragraph(f"Date: {m.get('datetime', '').replace('T', ' ')}")
    doc.add_paragraph(f"Attendees: {_attendees(m)}")
    if m.get("agenda", "").strip():
        doc.add_heading("Agenda", level=1)
        doc.add_paragraph(m["agenda"].strip())
    doc.add_heading("Key Discussions", level=1)
    for t in m["topics"]:
        p = doc.add_paragraph(style="List Number")
        p.add_run(t["title"] + ": ").bold = True
        p.add_run(t["summary"])
    doc.add_heading("Decisions", level=1)
    for d in m["decisions"]:
        doc.add_paragraph(d["statement"], style="List Number")
    doc.add_heading("Action Items", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ["Task", "Owner", "Deadline", "Status"]):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for a in m["actionItems"]:
        row = table.add_row().cells
        row[0].text, row[1].text = a["task"], a["owner"]
        row[2].text, row[3].text = a["due"] or "-", a["status"]
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def to_pdf(m: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body = styles["BodyText"]

    def para(text: str, style=body):
        return Paragraph(escape(text), style)

    story = [
        para(f"Minutes of Meeting: {m['title']}", styles["Title"]),
        para(f"Date: {m.get('datetime', '').replace('T', ' ')}"),
        para(f"Attendees: {_attendees(m)}"),
        Spacer(1, 10),
    ]
    if m.get("agenda", "").strip():
        story += [para("Agenda", styles["Heading2"]), para(m["agenda"].strip())]
    story.append(para("Key Discussions", styles["Heading2"]))
    for i, t in enumerate(m["topics"], 1):
        story.append(Paragraph(f"{i}. <b>{escape(t['title'])}</b>: {escape(t['summary'])}", body))
    story.append(para("Decisions", styles["Heading2"]))
    for i, d in enumerate(m["decisions"], 1):
        story.append(para(f"{i}. {d['statement']}"))
    story.append(para("Action Items", styles["Heading2"]))
    rows = [["Task", "Owner", "Deadline", "Status"]] + [
        [Paragraph(escape(a["task"]), body), Paragraph(escape(a["owner"]), body), a["due"] or "-", a["status"]]
        for a in m["actionItems"]
    ]
    table = Table(rows, colWidths=[250, 90, 70, 50], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4).build(story)
    return buf.getvalue()


def render(m: dict, fmt: str) -> tuple[bytes, str, str]:
    """Return (file bytes, media type, filename)."""
    if fmt == "md":
        data = to_markdown(m).encode("utf-8")
    elif fmt == "docx":
        data = to_docx(m)
    elif fmt == "pdf":
        data = to_pdf(m)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
    return data, MEDIA_TYPES[fmt], f"minutes.{fmt}"
