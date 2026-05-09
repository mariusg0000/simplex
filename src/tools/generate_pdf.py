import subprocess
from pathlib import Path

import fitz

SAFE_ZONE = 20


def _weasyprint_convert(html_path: str, pdf_path: str) -> tuple[bool, str]:
    if not Path(html_path).exists():
        return False, f"HTML file not found: {html_path}. Call write_html(content='...') first to create it."

    try:
        result = subprocess.run(
            ['weasyprint', html_path, pdf_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                return False, stderr
            return False, f"weasyprint exited with code {result.returncode}"

        stderr_lines = result.stderr.strip()
        if not Path(pdf_path).exists():
            return False, "weasyprint did not produce a PDF file"

        if stderr_lines:
            return True, stderr_lines

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "weasyprint timed out after 60 seconds"
    except FileNotFoundError:
        return False, "weasyprint not found on system PATH"
    except Exception as e:
        return False, f"weasyprint error: {str(e)}"


def _check_overlaps_via_fitz(pdf_path: str) -> tuple[bool, str]:
    try:
        doc = fitz.open(pdf_path)
        issues = []

        for page_num, page in enumerate(doc):
            blocks = page.get_text("blocks")
            for i, b1 in enumerate(blocks):
                x1, y1, x2, y2, _, block_type, _ = b1
                if block_type != 0:
                    continue
                for j, b2 in enumerate(blocks):
                    if j <= i:
                        continue
                    x3, y3, x4, y4, _, block_type2, _ = b2
                    if block_type2 != 0:
                        continue

                    if x1 < x4 and x2 > x3 and y1 < y4 and y2 > y3:
                        ox = min(x2, x4) - max(x1, x3)
                        oy = min(y2, y4) - max(y1, y3)
                        issues.append(
                            f"Block {i} overlaps Block {j} "
                            f"(page {page_num + 1}, {int(ox)}x{int(oy)}px)"
                        )

        doc.close()

        if issues:
            return False, "\n".join(issues[:10])
        return True, ""
    except Exception as e:
        return False, f"overlap check error: {str(e)}"


def _check_overflow_via_fitz(pdf_path: str, margin: int = SAFE_ZONE) -> tuple[bool, str]:
    try:
        doc = fitz.open(pdf_path)
        issues = []

        for page_num, page in enumerate(doc):
            page_rect = page.rect
            page_w = page_rect.width
            page_h = page_rect.height

            blocks = page.get_text("blocks")
            for i, block in enumerate(blocks):
                x1, y1, x2, y2, _, block_type, _ = block
                if block_type != 0:
                    continue

                if x2 > page_w - margin:
                    issues.append(
                        f"Block {i} at x={int(x2)}px exceeds page width {int(page_w)}px "
                        f"(+{int(x2 - (page_w - margin))}px) page {page_num + 1}"
                    )
                if y2 > page_h - margin:
                    issues.append(
                        f"Block {i} at y={int(y2)}px exceeds page height {int(page_h)}px "
                        f"(+{int(y2 - (page_h - margin))}px) page {page_num + 1}"
                    )

        doc.close()

        if issues:
            return False, "\n".join(issues[:10])
        return True, ""
    except Exception as e:
        return False, f"overflow check error: {str(e)}"


def get_description() -> dict:
    return {
        "description": "Convert HTML file to PDF with deterministic validation. Stages: WeasyPrint conversion -> overlap check -> overflow check. On success the agent terminates automatically — do NOT call any done/finish tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "html_path": {
                    "type": "string",
                    "description": "Absolute path to the HTML file to convert (auto-managed in agent context).",
                },
            },
            "required": [],
        },
    }


async def execute(html_path: str = None, _agent_params: dict = None) -> str:
    if _agent_params and not html_path:
        html_path = _agent_params.get("html_path")
    if not html_path:
        return "PDF_ERROR: no html_path available"

    pdf_path = str(Path(html_path).with_suffix('.pdf'))

    ok, msg = _weasyprint_convert(html_path, pdf_path)
    if not ok:
        return f"PDF_ERROR: weasyprint\n{msg}"

    ok, msg = _check_overlaps_via_fitz(pdf_path)
    if not ok:
        return f"PDF_ERROR: overlaps\n{msg}"

    ok, msg = _check_overflow_via_fitz(pdf_path)
    if not ok:
        return f"PDF_ERROR: overflow\n{msg}"

    # On success, return "_AGENT_DONE_: <path>" which signals the agent loop
    # to terminate immediately without an extra LLM round. This eliminates
    # the need for a separate done_tool / pdf_done tool call after success.
    # On error, return "PDF_ERROR: <reason>" so the LLM can retry.
    return f"_AGENT_DONE_: {pdf_path}"
