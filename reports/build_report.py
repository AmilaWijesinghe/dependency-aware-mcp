"""Build the report drafts from Markdown and verify the local benchmark evidence.

Uses the Python standard library for Word output and installed PyMuPDF for PDF.
Does not import the application, contact services, or change benchmark exports.
"""

from __future__ import annotations

import ast
import csv
import html
import json
import math
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent / "backend"
BENCHMARKS = ROOT / "benchmarks"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def verify_evidence() -> dict:
    def read(name):
        with (BENCHMARKS / name).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    rows = read("benchmark_results.csv")
    assert len(rows) == 400
    assert len({r["benchmarkId"] for r in rows}) == 1
    assert len({r["runId"] for r in rows}) == 400
    assert len({r["resourceKey"] for r in rows}) == 400
    assert len({(r["protocol"], r["scenarioId"], r["repetition"]) for r in rows}) == 400
    assert set(Counter((r["protocol"], r["scenarioId"]) for r in rows).values()) == {10}
    assert not any(r["error"].strip() for r in rows)
    assert all(int(r["inputTokens"]) + int(r["outputTokens"]) == int(r["totalTokens"]) for r in rows)

    scenario_ast = ast.parse((PROJECT / "app/evaluation/heldout_scenarios.py").read_text(encoding="utf-8"))
    expected = {}
    for node in ast.walk(scenario_ast):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BenchmarkScenario":
            fields = {kw.arg: kw.value for kw in node.keywords}
            expected[ast.literal_eval(fields["scenario_id"])] = ast.literal_eval(fields["expected_final"])
    assert len(expected) == 10
    for row in rows:
        assert (ast.literal_eval(row["finalValue"]) == expected[row["scenarioId"]]) == (row["correct"] == "True")

    summary_map = {
        "mean_latency_ms": "elapsedMs", "mean_input_tokens": "inputTokens",
        "mean_output_tokens": "outputTokens", "mean_tokens": "totalTokens",
        "mean_wasted_tokens": "wastedTokens", "mean_conflicts": "conflicts",
        "mean_retries": "retries", "mean_lock_wait_ms": "lockWaitMs",
        "mean_nodes_reexecuted": "nodesReexecuted", "mean_nodes_preserved": "nodesPreserved",
    }
    for exported in read("benchmark_summary.csv"):
        group = [r for r in rows if r["protocol"] == exported["protocol"]]
        assert len(group) == int(exported["runs"])
        assert sum(r["correct"] == "True" for r in group) == int(exported["successful_runs"])
        for aggregate, raw in summary_map.items():
            actual = statistics.mean(float(r[raw]) for r in group)
            assert math.isclose(actual, float(exported[aggregate]), rel_tol=1e-9, abs_tol=1e-8)
        for prefix, function in [("median", statistics.median), ("std", statistics.stdev)]:
            for suffix, raw in [("latency_ms", "elapsedMs"), ("tokens", "totalTokens")]:
                actual = function(float(r[raw]) for r in group)
                assert math.isclose(actual, float(exported[f"{prefix}_{suffix}"]), rel_tol=1e-9, abs_tol=1e-8)

    dep = [r for r in rows if r["protocol"] == "dependency_occ"]
    matrix = Counter((r["semanticGroundTruth"], r["semanticPrediction"]) for r in dep)
    assert matrix == {("disruptive", "disruptive"): 40, ("disruptive", "non_disruptive"): 10,
                      ("non_disruptive", "disruptive"): 10, ("non_disruptive", "non_disruptive"): 40}
    assert {r["scenarioId"] for r in dep if r["correct"] == "False"} == {"ho_d_reduce_current_price_by_8"}
    nd2 = [r for r in dep if r["scenarioId"] == "ho_nd_fixed_quantity_vs_price"]
    assert math.isclose(statistics.mean(int(r["wastedTokens"]) for r in nd2), 483.7)
    evidence = {
        "benchmark_id": rows[0]["benchmarkId"], "records": len(rows),
        "checks": {
            "balanced_complete_design": True, "unique_runs_and_resources": True,
            "no_recorded_execution_errors": True, "token_arithmetic": True,
            "all_correctness_flags_match_scenario_oracles": True,
            "protocol_summary_means_medians_and_standard_deviations_match_raw": True,
            "confusion_matrix_verified": True, "failure_scenario_verified": True,
        },
        "correct_by_protocol": {p: sum(r["correct"] == "True" for r in rows if r["protocol"] == p)
                                for p in ["naive", "2pl", "occ", "dependency_occ"]},
        "confusion_matrix": {f"{a} -> {b}": n for (a, b), n in matrix.items()},
        "method": "Read-only verification of existing exports; no benchmark rerun.",
    }
    (ROOT / "evidence_checks.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def blocks(source):
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            content = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                content.append(lines[i])
                i += 1
            yield "code", "\n".join(content)
            i += 1
        elif line.startswith("|"):
            table = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    table.append(cells)
                i += 1
            yield "table", table
        elif re.match(r"^#{1,3} ", line):
            level, title = line.split(" ", 1)
            yield f"h{len(level)}", title
            i += 1
        elif line == "---":
            yield "rule", ""
            i += 1
        elif line.startswith("- "):
            yield "bullet", line[2:]
            i += 1
        else:
            content = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "```", "- ")):
                content.append(lines[i])
                i += 1
            yield "p", " ".join(content)


def inline_html(value):
    parts = re.split(r"(`[^`]+`|\*\*.+?\*\*)", value)
    return "".join("<code>" + html.escape(p[1:-1]) + "</code>" if p.startswith("`") else
                   "<strong>" + html.escape(p[2:-2]) + "</strong>" if p.startswith("**") else html.escape(p)
                   for p in parts)


def make_html(items):
    body = []
    for kind, value in items:
        if kind == "table":
            body.append("<table>")
            for i, row in enumerate(value):
                tag = "th" if i == 0 else "td"
                body.append("<tr>" + "".join(f"<{tag}>{inline_html(c)}</{tag}>" for c in row) + "</tr>")
            body.append("</table>")
        elif kind == "code":
            body.append("<pre>" + html.escape(value) + "</pre>")
        elif kind == "bullet":
            body.append("<p class='note'>• " + inline_html(value) + "</p>")
        elif kind == "rule":
            body.append("<hr>")
        else:
            attrs = " class='chapter'" if kind == "h1" else ""
            body.append(f"<{kind}{attrs}>" + inline_html(value) + f"</{kind}>")
    css = """
    body { font-family: 'Times New Roman', serif; font-size: 11pt; line-height: 1.4; color: #18202a; }
    h1 { font-size: 18pt; color: #162b43; margin-bottom: 20pt; }
    h1.chapter { margin-top: 24pt; }
    h2 { font-size: 13pt; margin-top: 18pt; margin-bottom: 9pt; color: #162b43; page-break-after: avoid; }
    h3 { font-size: 11.5pt; margin-top: 13pt; margin-bottom: 7pt; page-break-after: avoid; }
    p { margin: 0 0 9pt 0; text-align: justify; }
    table { width: 100%; border-collapse: collapse; margin: 8pt 0 14pt 0; font-size: 8.5pt; }
    td, th { border: 0.5pt solid #a6b3c0; padding: 4pt; text-align: left; vertical-align: top; }
    th { font-weight: bold; }
    code { font-family: monospace; font-size: 8.5pt; overflow-wrap: anywhere; }
    pre { font-family: monospace; font-size: 6.8pt; line-height: 1.3; white-space: pre; }
    .note { font-size: 9pt; }
    """
    return "<!doctype html><html><head><meta charset='utf-8'><title>Final report: Chapters 3 and 4</title><style>" + css + "</style></head><body>" + "\n".join(body) + "</body></html>"


def run_xml(text, *, bold=False, code=False, size=None):
    properties = ("<w:b/>" if bold else "")
    if code:
        properties += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'
    if size:
        properties += f'<w:sz w:val="{size}"/>'
    return f'<w:r><w:rPr>{properties}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def inline_xml(value, size=None):
    parts = re.split(r"(`[^`]+`|\*\*.+?\*\*)", value)
    return "".join(run_xml(p[1:-1], code=True, size=size or 20) if p.startswith("`") else
                   run_xml(p[2:-2], bold=True, size=size) if p.startswith("**") else run_xml(p, size=size)
                   for p in parts)


def paragraph(value, style="Normal", extra="", size=None):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{extra}</w:pPr>{inline_xml(value, size)}</w:p>'


def make_docx(items):
    content = []
    chapter = 0
    for kind, value in items:
        if kind == "table":
            columns = len(value[0])
            width = 9360 // columns
            content.append('<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
                           '<w:tblBorders>' + ''.join(f'<w:{side} w:val="single" w:sz="4" w:color="A6B3C0"/>'
                           for side in ['top','left','bottom','right','insideH','insideV']) +
                           '</w:tblBorders><w:tblCellMar><w:top w:w="70" w:type="dxa"/><w:left w:w="85" w:type="dxa"/>'
                           '<w:bottom w:w="70" w:type="dxa"/><w:right w:w="85" w:type="dxa"/></w:tblCellMar></w:tblPr>'
                           '<w:tblGrid>' + f'<w:gridCol w:w="{width}"/>' * columns + '</w:tblGrid>')
            for i, row in enumerate(value):
                content.append('<w:tr><w:trPr><w:cantSplit/>' + ('<w:tblHeader/>' if i == 0 else '') + '</w:trPr>')
                for cell in row:
                    shade = '<w:shd w:fill="E8EEF5"/>' if i == 0 else ''
                    content.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>' +
                                   paragraph(('**' + cell + '**') if i == 0 else cell, "TableText", size=17) + '</w:tc>')
                content.append('</w:tr>')
            content.append('</w:tbl>' + paragraph('', "TableText"))
        elif kind == "code":
            for line in value.splitlines():
                content.append('<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr>' + run_xml(line, code=True, size=14) + '</w:p>')
        elif kind == "rule":
            content.append(paragraph('', extra='<w:pBdr><w:bottom w:val="single" w:sz="4" w:color="A6B3C0"/></w:pBdr>'))
        elif kind.startswith("h"):
            level = kind[1]
            extra = ''
            if kind == 'h1':
                if chapter:
                    extra = '<w:pageBreakBefore/>'
                chapter += 1
            content.append(paragraph(value, 'Heading' + level, extra))
        elif kind == "bullet":
            content.append(paragraph('• ' + value, 'Note'))
        elif value.startswith('**Table ') or value.startswith('**Figure '):
            content.append(paragraph(value, 'Caption'))
        else:
            content.append(paragraph(value))

    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<w:body>' + ''.join(content) +
                '<w:sectPr><w:footerReference w:type="default" r:id="rId2"/>'
                '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1273" w:bottom="1440" w:left="1273" '
                'w:header="600" w:footer="600"/><w:cols w:space="720"/></w:sectPr></w:body></w:document>')
    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:styles xmlns:w="{W}">
      <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>
      <w:sz w:val="24"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>
      <w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults>
      <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:jc w:val="both"/></w:pPr></w:style>
      <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
        <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="300"/><w:outlineLvl w:val="0"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="34"/><w:color w:val="162B43"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
        <w:pPr><w:keepNext/><w:spacing w:before="260" w:after="140"/><w:outlineLvl w:val="1"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="27"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
        <w:pPr><w:keepNext/><w:spacing w:before="200" w:after="120"/><w:outlineLvl w:val="2"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/>
        <w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/></w:pPr><w:rPr><w:sz w:val="17"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/>
        <w:pPr><w:keepNext/><w:spacing w:before="160" w:after="100"/><w:jc w:val="left"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>
        <w:pPr><w:keepNext/><w:spacing w:after="0" w:line="200" w:lineRule="auto"/><w:jc w:val="left"/></w:pPr></w:style>
      <w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Author Note"/><w:basedOn w:val="Normal"/>
        <w:pPr><w:spacing w:after="100" w:line="260" w:lineRule="auto"/><w:jc w:val="left"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
    </w:styles>'''
    types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
    <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
    </Types>'''
    rootrels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    </Relationships>'''
    docrels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
    </Relationships>'''
    footer = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:ftr xmlns:w="{W}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:t>Chapter 3 and 4 draft | </w:t></w:r>
    <w:fldSimple w:instr="PAGE"/></w:p></w:ftr>'''
    path = ROOT / 'chapters_3_and_4.docx'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in {'[Content_Types].xml': types, '_rels/.rels': rootrels,
                           'word/document.xml': document, 'word/styles.xml': styles,
                           'word/_rels/document.xml.rels': docrels, 'word/footer1.xml': footer}.items():
            ET.fromstring(data)
            archive.writestr(name, data.encode('utf-8'))
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        tree = ET.fromstring(archive.read('word/document.xml'))
        assert len(tree.findall(f'.//{{{W}}}tbl')) == 12
    return path


def make_pdf(html_text):
    import pymupdf
    temporary = ROOT / 'report_layout.pdf'
    writer = pymupdf.DocumentWriter(str(temporary))
    mediabox = pymupdf.paper_rect('a4')
    area = mediabox + (55, 52, -55, -52)
    pages_written = 0
    head, body = html_text.split('<body>', 1)
    body = body.removesuffix('</body></html>')
    chapter_marker = "<h1 class='chapter'>Chapter 04: RESULTS</h1>"
    chapter_three, chapter_four = body.split(chapter_marker, 1)
    for segment in [chapter_three, chapter_marker + chapter_four]:
        story = pymupdf.Story(html=head + '<body>' + segment + '</body></html>')
        more = True
        while more:
            device = writer.begin_page(mediabox)
            more, _ = story.place(area)
            story.draw(device)
            writer.end_page()
            pages_written += 1
            if pages_written > 60:
                writer.close()
                raise RuntimeError('PDF layout exceeded 60 pages; inspect unbreakable content')
    writer.close()
    del writer
    document = pymupdf.open(temporary)
    for i, page in enumerate(document):
        page.insert_text((55, 817), f'Chapter 3 and 4 draft  |  {i+1}', fontsize=8, color=(0.35, 0.4, 0.45))
    document.set_metadata({'title': 'Dependency-Aware MCP: Chapters 3 and 4', 'subject': 'Methodology and Results draft'})
    output = ROOT / 'chapters_3_and_4.pdf'
    document.save(output)
    count = len(document)
    text = '\n'.join(page.get_text() for page in document)
    assert 'METHODOLOGY' in text and 'RESULTS' in text and '64.07%' in text
    assert 'Source and completion notes' in text
    for page_no in [0, 1, min(8, count-1)]:
        document[page_no].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(ROOT / f'preview_page_{page_no+1}.png')
    document.close()
    temporary.unlink()
    return count


def main():
    evidence = verify_evidence()
    source = (ROOT / 'chapters_3_and_4.md').read_text(encoding='utf-8')
    items = list(blocks(source))
    html_text = make_html(items)
    (ROOT / 'chapters_3_and_4.html').write_text(html_text, encoding='utf-8')
    docx_path = make_docx(items)
    page_count = make_pdf(html_text)
    print(json.dumps({'evidence_checks': evidence['checks'], 'word_count': len(source.split()),
                      'tables': sum(k == 'table' for k, v in items), 'pdf_pages': page_count,
                      'word_document': str(docx_path)}, indent=2))


if __name__ == '__main__':
    main()
