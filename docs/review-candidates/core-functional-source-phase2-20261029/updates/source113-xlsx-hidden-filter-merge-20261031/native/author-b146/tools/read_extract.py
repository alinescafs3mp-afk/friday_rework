"""Document-to-text extraction for ``read_file``: stdlib Jupyter/DOCX/XLSX (always
authoritative for those three), plus legacy Office/OpenDocument/RTF/EPUB/PDF when the
optional ``firecrawl-anydoc`` package (imports as ``anydoc``) is installed. Malformed
documents raise :class:`ExtractionError`; callers fall back to text/binary handling."""

from __future__ import annotations

import contextlib
import functools
import importlib
import itertools
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable, Iterator, Optional
from xml.etree import ElementTree as ET

__all__ = ["EXTRACTABLE_EXTENSIONS", "ExtractionError", "extract_document_bytes",
           "extract_document_text", "is_extractable_document"]

EXTRACTABLE_EXTENSIONS = frozenset({".ipynb", ".docx", ".xlsx", ".db", ".sqlite", ".sqlite3"})
ANYDOC_EXTENSIONS = frozenset({
    ".doc", ".docm", ".ppt", ".pps", ".pot", ".pptx", ".pptm", ".ppsx", ".ppsm",
    ".xls", ".xlsm", ".xlsb", ".odt", ".ods", ".odp", ".rtf", ".epub", ".pdf"})
# anydoc loads whole files (no streaming); read_file's char budget applies only post-conversion.
MAX_ANYDOC_BYTES = 50 * 1024 * 1024
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
_MAX_XLSX_ROWS_PER_SHEET = 5000
_MAX_XLSX_COLS = 256
_MAX_XLSX_FORMULA_RECORDS = 512
_MAX_XLSX_FORMULA_TEXT_CHARS = 4096
_MAX_XLSX_FORMULA_RECORD_BYTES = 32768
_MAX_XLSX_FORMULA_PREVIEW_BYTES = 128000
_MAX_XLSX_STRUCTURE_RECORDS = 512
_MAX_XLSX_STRUCTURE_RECORD_BYTES = 32768
_MAX_XLSX_STRUCTURE_PREVIEW_BYTES = 128000
_MAX_XLSX_STRUCTURE_TEXT_CHARS = 4096
_MAX_XLSX_MERGE_RANGES = 256
_MAX_XLSX_MERGE_CELLS = 4096

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


class ExtractionError(Exception):
    """Raised when a supported-looking document cannot be rendered as text."""


def _extension(path: str) -> str:
    ext = Path(path).suffix.lower()
    known = ext in EXTRACTABLE_EXTENSIONS or (ext in ANYDOC_EXTENSIONS and _anydoc() is not None)
    return ext if known else ""


_ANYDOC_UNSET = object()
_anydoc_module: Any = _ANYDOC_UNSET
_anydoc_lock = threading.Lock()
# Cooldown after a failed load: the attempt can shell out to pip, so retrying every call would
# hammer the network where install can't succeed.
ANYDOC_RETRY_SECONDS = 300.0
_anydoc_failed_at: Optional[float] = None


def _anydoc() -> Optional[Any]:
    """Lazily import the optional anydoc converter (None when unavailable; failures retried after
    ANYDOC_RETRY_SECONDS so one transient pip/network blip does not stick)."""
    global _anydoc_module, _anydoc_failed_at
    if _anydoc_module is not _ANYDOC_UNSET:
        return _anydoc_module
    with _anydoc_lock:
        if _anydoc_module is not _ANYDOC_UNSET:
            return _anydoc_module
        if (_anydoc_failed_at is not None
                and time.monotonic() - _anydoc_failed_at < ANYDOC_RETRY_SECONDS):
            return None
        try:
            from pm import ensure_import

            # read_file must never block on an install prompt.
            ensure_import("doc-extract")
        except Exception:
            _anydoc_failed_at = time.monotonic()
            return None
        try:            _anydoc_module = importlib.import_module("anydoc")
        except Exception:  # install failure, ImportError or a broken native binding
            _anydoc_failed_at = time.monotonic()
            return None
        _anydoc_failed_at = None
    return _anydoc_module  # type: ignore[return-value]


def is_extractable_document(path: str) -> bool:
    return bool(_extension(path))


def _check_size(size: int, limit: int) -> None:
    if size > limit:
        raise ExtractionError(f"Document too large to convert ({size:,} bytes, limit is {limit:,})")


@contextlib.contextmanager
def _temp_copy(data: bytes, suffix: str) -> Iterator[str]:
    """Materialize backend bytes in a private host temp file; removed even when parsing fails."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(data)
    try:
        yield fh.name
    finally:
        with contextlib.suppress(OSError):
            os.unlink(fh.name)


def extract_document_text(path: str) -> str:
    ext = _extension(path)
    if ext in _STDLIB_EXTRACTORS:
        return _STDLIB_EXTRACTORS[ext](path)
    if ext in ANYDOC_EXTENSIONS:
        return _extract_anydoc(path)
    raise ExtractionError(f"Unsupported document type: {path!r}")


def extract_document_bytes(data: bytes, path: str) -> str:
    """Extract a document already fetched across a file backend boundary."""
    _check_size(len(data), MAX_DOCUMENT_BYTES)
    ext = _extension(path)
    if ext in ANYDOC_EXTENSIONS:
        return _extract_anydoc_bytes(data, path)
    if ext not in EXTRACTABLE_EXTENSIONS:
        raise ExtractionError(f"Unsupported document type: {path!r}")
    with _temp_copy(data, ext) as temp_path:  # the stdlib extractors are path-oriented
        if ext == ".ipynb":
            return _extract_notebook(temp_path, display_path=path)
        return _STDLIB_EXTRACTORS[ext](temp_path)


class ScopedExtractionError(ExtractionError):
    """Bounded format failure for the descriptor-only ordinary document lane."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def extract_scoped_document_bytes(data: bytes, format: str) -> str:
    """Convert own immutable snapshots; never install or use hosted OCR.

    DOCX/XLSX reuse bounded native parsers. PDF keeps the existing installed
    anydoc text route, with a bounded networkless local OCR fallback only for
    its scanned-page signal. OCR returns a string-compatible trusted metadata
    result; neither route establishes exact image content or raw write authority.
    """
    if not isinstance(data, bytes) or len(data) > 1000000:
        raise ScopedExtractionError('input_limit')
    if format == 'docx':
        try:
            text = _extract_docx(io.BytesIO(data), max_xml_bytes=1000000)
        except (ExtractionError, ValueError, RuntimeError, NotImplementedError, LookupError, zlib.error):
            raise ScopedExtractionError('malformed_or_required_part_limit') from None
    elif format == 'xlsx':
        try:
            text = _extract_xlsx(io.BytesIO(data), max_xml_bytes=1000000,
                                 max_total_xml_bytes=1000000, include_inventory=True)
        except (ExtractionError, ValueError, RuntimeError, NotImplementedError, LookupError, zlib.error):
            raise ScopedExtractionError('malformed_or_required_part_limit') from None
    elif format == 'pdf':
        try:
            module = importlib.import_module('anydoc')  # direct import, no pm loader
        except (ImportError, OSError):
            raise ScopedExtractionError('missing_local_converter') from None
        try:
            text = module.to_markdown_bytes(data, format='pdf', ocr='reject')
        except Exception as exc:
            needs_ocr = getattr(module, 'NeedsOcrError', None)
            if needs_ocr is None or not isinstance(exc, needs_ocr):
                raise ScopedExtractionError('malformed_or_unsupported') from None
            from tools.scoped_pdf_ocr import extract_local_pdf, LocalOCRFailure
            try:
                text = extract_local_pdf(data)
            except LocalOCRFailure as error:
                raise ScopedExtractionError(str(error)) from None
        else:
            text = _pdf_scoped_page_view(data, text)
    else:
        raise ScopedExtractionError('unsupported_format')
    if not isinstance(text, str) or not text.strip():
        raise ScopedExtractionError('no_extractable_text')
    if len(text.encode('utf-8')) > 1000000:
        raise ScopedExtractionError('extracted_text_limit')
    return text


def _anydoc_missing_error(path: str) -> str:
    """Teaching text for anydoc-gated formats (not in the schema: only sessions hitting one pay).

    Response-time hint (#95681 pattern): the schema no longer lists the anydoc-gated formats or the
    availability caveat — a session that never touches a .doc/.odt/.epub never pays for the explanation, and
    one that does gets the full story here, with the fix.
    """
    return (
        f"Cannot convert {path!r}: this format needs the optional anydoc "
        "converter, which is not installed (install blocked or first "
        "attempt failed; retried every 5 minutes). Run `hermes pm repair` "
        "to restore firecrawl-anydoc, or convert the file "
        "yourself via terminal (e.g. libreoffice --headless --convert-to "
        "txt).")


def _hosted_ocr_config() -> tuple:
    """(enabled, api_key, api_url); never raises, no network. Maintainer decision: the ONLY route
    is a direct ``FIRECRAWL_API_KEY`` (anydoc defaults api_url); the Nous gateway's Parse proxy
    live-probed broken, so it is NOT used. ``file_tools.hosted_ocr: false`` disables even with a
    key. The key is a profile credential: read through the secret scope so a multiplexed
    secondary never spends (or reveals its documents to) the default profile's Firecrawl key."""
    from agent.secret_scope import get_secret
    api_key = get_secret("FIRECRAWL_API_KEY") or None
    enabled = api_key is not None
    with contextlib.suppress(Exception):
        from hermes_cli.config import load_config_readonly
        section = load_config_readonly().get("file_tools")
        if isinstance(section, dict) and section.get("hosted_ocr") is False:
            enabled = False
    return enabled, api_key, None


def hosted_ocr_available() -> bool:
    """Probe for read_file's schema line; a key failing at conversion time surfaces in NEEDS-OCR."""
    return _hosted_ocr_config()[0]


def _needs_ocr_warning(path: str, pages, hosted_error: str = "") -> str:
    """NeedsOcrError result when hosted OCR is off/failed; hints at CHECKING for an OCR skill
    (never names one) and never advertises the hosted_ocr knob."""
    page_list = ", ".join(str(p) for p in pages) if pages else "unknown"
    hosted = f"Hosted OCR was attempted and failed ({hosted_error}). " if hosted_error else ""
    return (
        f"[NEEDS OCR: pages {page_list} of this PDF are scanned images "
        f"with no text layer — their content is MISSING below. {hosted}"
        "If the missing pages matter: render just those pages with "
        f"`pdftoppm -jpeg -r 150 -f <first> -l <last> {shlex.quote(path)} $TMPDIR/page` "
        "and inspect via vision_analyze, or check whether an OCR skill is "
        "available (skills_list).]\n")


def _finalize_anydoc_text(text: Any, path: str, pdf_note: Callable[[], str]) -> str:
    """Normalize converter output; PDFs get the coverage note PREPENDED (read_file paginates, so a
    footer may never be fetched) — this covers PARTIAL scan gaps that raise no NeedsOcrError."""
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("Document contains no extractable text")
    return (pdf_note() if Path(path).suffix.lower() == ".pdf" else "") + text.rstrip("\n") + "\n"


def _ocr_scanned_pdf(mod: Any, path: str, exc: BaseException) -> str:
    """anydoc >= 0.2 scanned-pages signal: hosted OCR when a route exists, else teach recovery."""
    pages = list(getattr(exc, "pages", []) or [])
    enabled, api_key, api_url = _hosted_ocr_config()
    hosted_error = ""
    if enabled:
        try:
            extra = {k: v for k, v in (("api_key", api_key), ("api_url", api_url)) if v}
            return mod.to_markdown(path, ocr="hosted", **extra).rstrip("\n") + "\n"
        except Exception as hosted_exc:  # noqa: BLE001
            hosted_error = f"{type(hosted_exc).__name__}: {hosted_exc}"
    return _needs_ocr_warning(path, pages, hosted_error)  # whole doc is scans: the warning IS it


def _extract_anydoc(path: str) -> str:
    mod = _anydoc()
    if mod is None:
        raise ExtractionError(_anydoc_missing_error(path))
    try:
        _check_size(os.path.getsize(path), MAX_ANYDOC_BYTES)
        text = mod.to_markdown(path)
    except ExtractionError:
        raise
    except OSError as exc:
        raise ExtractionError(str(exc)) from exc
    except Exception as exc:
        needs_ocr = getattr(mod, "NeedsOcrError", None)
        if needs_ocr is not None and isinstance(exc, needs_ocr):
            return _ocr_scanned_pdf(mod, path, exc)
        # Any ConvertError subclass (Unsupported/Malformed/Encrypted/...) = "no meaningful text".
        raise ExtractionError(f"{type(exc).__name__}: {exc}") from exc
    return _finalize_anydoc_text(text, path, lambda: _pdf_coverage_note(path))


def _extract_anydoc_bytes(data: bytes, path: str) -> str:
    mod = _anydoc()
    if mod is None:
        raise ExtractionError(_anydoc_missing_error(path))
    _check_size(len(data), MAX_ANYDOC_BYTES)
    try:
        text = mod.to_markdown_bytes(data)
    except Exception as exc:
        raise ExtractionError(f"{type(exc).__name__}: {exc}") from exc
    return _finalize_anydoc_text(text, path, lambda: _pdf_coverage_note_from_bytes(data, path))


# ── Scanned-PDF coverage: text-layer extractors return nothing for scanned pages, so a mostly
# scanned PDF converts "successfully" into silent data loss. Count per-page text via pdftotext.
PDF_EMPTY_PAGE_CHARS = 20  # fewer extracted chars than this = empty page
# Warn when empty pages reach both MIN_EMPTY and MIN_RATIO, or ABSOLUTE_EMPTY alone.
PDF_COVERAGE_MIN_EMPTY, PDF_COVERAGE_MIN_RATIO, PDF_COVERAGE_ABSOLUTE_EMPTY = 2, 0.2, 10
PDF_PAGE_SCAN_TIMEOUT = 20.0
PDF_GAP_MAP_MAX_ENTRIES = 20  # cap so alternating text/scan pages can't balloon the warning
_GAP_CONTEXT_CHARS = 60


def _pdf_page_texts(path: str) -> Optional[list[str]]:
    """Per-page extracted text, or None when undeterminable."""
    if shutil.which("pdftotext") is None:
        return None
    try:
        proc = subprocess.run(
            ["pdftotext", path, "-"], capture_output=True, timeout=PDF_PAGE_SCAN_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""
    pages = out.split("\f") if out else []
    if pages and not pages[-1].strip():
        pages.pop()  # trailing form-feed artifact
    return pages or None


def _gap_map(counts: list[int], texts: list[str], empty: list[int]) -> str:
    """Per-gap breakdown labeled with the text before each gap, so the agent picks which to OCR."""
    # Sorted 1-based page numbers -> (start, end) runs; consecutive pages share ``page - index``.
    runs = [list(g) for _k, g in itertools.groupby(enumerate(empty), lambda e: e[1] - e[0])]
    ranges = [(run[0][1], run[-1][1]) for run in runs]
    lines: list[str] = []
    for a, b in ranges[:PDF_GAP_MAP_MAX_ENTRIES]:
        label = ""
        for prev in range(a - 2, -1, -1):  # nearest preceding page with text
            if counts[prev] >= PDF_EMPTY_PAGE_CHARS:
                snippet = " ".join(texts[prev].split())[:_GAP_CONTEXT_CHARS]
                label = f' — after "{snippet}" (p{prev + 1})'
                break
        span = f"page {a}" if a == b else f"pages {a}-{b}"
        n = b - a + 1
        lines.append(f"  {span} ({n} page{'s' if n != 1 else ''}){label}")
    if len(ranges) > PDF_GAP_MAP_MAX_ENTRIES:
        rest = ranges[PDF_GAP_MAP_MAX_ENTRIES:]
        lines.append(f"  … {len(rest)} more gaps ({sum(b - a + 1 for a, b in rest)} pages)")
    return "\n".join(lines)


def _pdf_coverage_note(path: str, display_path: Optional[str] = None) -> str:
    """Warning header when many pages yielded no text, else ''. ``display_path`` (default ``path``,
    which may be a host temp file) is what the recovery command shows."""
    texts = _pdf_page_texts(path)
    if not texts or len(texts) < 2:
        return ""
    counts = [len(page.strip()) for page in texts]
    empty = [i + 1 for i, n in enumerate(counts) if n < PDF_EMPTY_PAGE_CHARS]
    total = len(counts)
    n_empty = len(empty)
    enough = n_empty / total >= PDF_COVERAGE_MIN_RATIO or n_empty >= PDF_COVERAGE_ABSOLUTE_EMPTY
    if n_empty < PDF_COVERAGE_MIN_EMPTY or not enough:
        return ""
    shown = display_path or path
    return (
        "[EXTRACTION COVERAGE WARNING: "
        f"{len(empty)} of {total} pages in this PDF yielded no text. "
        "Those pages are likely scanned images (or blank) — their content "
        "is MISSING from the extracted text below, even where section "
        "headers appear with empty bodies. Unreadable gaps, each labeled "
        "with the last text extracted before it:\n"
        f"{_gap_map(counts, texts, empty)}\n"
        "Decide which gaps you actually need — do NOT OCR or render "
        "everything. For the gaps that matter, render just that range with "
        f"`pdftoppm -jpeg -r 150 -f <first> -l <last> {shlex.quote(shown)} $TMPDIR/page` "
        "and inspect each image with the vision_analyze tool, or use the "
        "ocr-and-documents skill (marker-pdf) for bulk OCR of large "
        "ranges.]\n")


def _pdf_coverage_note_from_bytes(data: bytes, display_path: str) -> str:
    """Coverage note for backend PDF bytes via a host temp copy (pdftotext needs a path)."""
    with contextlib.suppress(OSError), _temp_copy(data, ".pdf") as temp_path:
        return _pdf_coverage_note(temp_path, display_path=display_path)
    return ""


def _pdf_scoped_page_view(data: bytes, text: str) -> str:
    """Prepend an authoritative per-page plain-text view to scoped PDF text.

    Each ``[page N]`` section holds exactly page N's own text layer from the
    existing local pdftotext pass over a private temp copy (the coverage-note
    mechanism), so page attribution inside the view is authoritative by
    construction. The complete converter text is retained after the view,
    unpaged: pdftotext can drop glyphs anydoc keeps, and mapping page
    boundaries onto converter text has twice attributed real content to the
    wrong page, so converter text never receives generated page markers. Undeterminable
    boundaries (no/failed pdftotext), or source text colliding with the view
    delimiters, return the exact unpaged text unchanged. The view is
    optional augmentation inside the caller's unchanged 1000000-byte UTF-8
    output budget: when view plus complete original would exceed it, the
    exact unpaged original is returned instead, so a previously readable
    document stays readable (numeric page citation is then honestly
    unavailable); an original over the budget on its own still fails at the
    caller's unchanged bound.
    """
    if shutil.which("pdftotext") is None:
        return text
    pages: Optional[list[str]] = None
    with contextlib.suppress(OSError), _temp_copy(data, ".pdf") as temp_path:
        pages = _pdf_page_texts(temp_path)
    if not pages:
        return text
    # Reserved view delimiters must never turn a source literal into a page boundary.
    if any(re.search(r"\[page \d+\]|\[end of page view", page) for page in pages):
        return text
    sections = [f"[page {number}]\n{page.strip()}" for number, page in enumerate(pages, start=1)]
    augmented = ("[PDF page view: per-page plain text from the local pdftotext extractor; "
                 "each [page N] section is that page's own text layer]\n"
                 + "\n\n".join(sections)
                 + "\n[end of page view — the complete unpaged document text follows; "
                   "the page numbers above do not apply to it]\n"
                 + text)
    if len(augmented.encode('utf-8')) > 1000000:
        return text
    return augmented


def _joined(lines: list[str], empty_error: str) -> str:
    """Join extracted lines with a single trailing newline; raise when nothing non-blank."""
    if not any(line.strip() for line in lines):
        raise ExtractionError(empty_error)
    return "\n".join(lines).rstrip("\n") + "\n"


def _source_text(source) -> str:
    """Notebook source/text fields are a str or a list of str fragments."""
    if isinstance(source, list):
        source = "".join(item for item in source if isinstance(item, str))
    return source if isinstance(source, str) else ""


def _human_size(n_bytes: int) -> str:
    return f"{round(n_bytes / 1024)} KB" if n_bytes >= 1024 else f"{n_bytes} B"


def _base64_bytes(payload: str) -> int:
    """Approximate decoded size of a base64 payload (whitespace ignored)."""
    clean = re.sub(r"[^0-9+/=A-Za-z]", "", payload)
    return max(0, (len(clean) * 3) // 4 - min(2, len(clean) - len(clean.rstrip("="))))


def _clean_stream_text(text: str) -> str:
    """Strip ANSI escapes; keep only the final ``\\r`` frame of each line (tqdm redraws)."""
    from tools.ansi_strip import strip_ansi
    return "\n".join(([f for f in line.split("\r") if f] or [""])[-1]
                     for line in strip_ansi(text).replace("\r\n", "\n").split("\n"))


_MAX_OUTPUT_CHARS = 20_000  # per code cell, so one runaway training log cannot flood the extraction
# nbformat v3 stores mime data flat on the output dict under these keys.
_V3_MIME_KEYS = (("png", "image/png"), ("jpeg", "image/jpeg"), ("svg", "image/svg+xml"), ("html", "text/html"))


def _notebook_output_text(output: Any) -> str:
    """One notebook output as compact text: stream/traceback/textual results kept; token-heavy
    payloads (images, HTML, widgets) become sized placeholders. Handles v4 and legacy v3 shapes."""
    if not isinstance(output, dict):
        return ""
    otype = output.get("output_type")
    if otype == "stream":
        body = _clean_stream_text(_source_text(output.get("text", "")))
        return body if body.strip() else ""
    if otype in {"error", "pyerr"}:
        tb = output.get("traceback")
        tb_text = _clean_stream_text("\n".join(filter(lambda l: isinstance(l, str), tb))
                                     if isinstance(tb, list) else "")
        header = f"Error: {output.get('ename', '')}: {output.get('evalue', '')}".rstrip(": ")
        return f"{header}\n{tb_text}".rstrip()
    if otype not in {"execute_result", "display_data", "pyout"}:
        return ""
    data = output.get("data")
    if not isinstance(data, dict):  # legacy v3: mime payloads sit flat on the output dict
        data = {"text/plain": output["text"]} if isinstance(output.get("text"), (str, list)) else {}
        data.update((mime, output[k]) for k, mime in _V3_MIME_KEYS if k in output)
    if "application/vnd.jupyter.widget-view+json" in data:
        return "[interactive widget — omitted]"
    for mime in ("text/plain", "text/markdown"):  # models consume text far better than markup
        body = _clean_stream_text(_source_text(data[mime])) if mime in data else ""
        if body.strip():
            return body
    for mime, value in data.items():
        if isinstance(mime, str) and mime.startswith("image/"):
            return f"[{mime} output — {_human_size(_base64_bytes(_source_text(value)))}, omitted]"
    if "text/html" in data:
        return f"[text/html output — {len(_source_text(data['text/html'])):,} chars, omitted]"
    return f"[{', '.join(str(m) for m in data) or 'unknown'} output — omitted]"


def _notebook_outputs(cell: dict, jq_pointer: str = "", filename: str = "") -> str:
    outputs = cell.get("outputs")
    if not isinstance(outputs, list):
        return ""
    joined = "\n".join(filter(None, map(_notebook_output_text, outputs)))
    if len(joined) <= _MAX_OUTPUT_CHARS:
        return joined
    hint = f" — full output: jq -r '{jq_pointer}' {shlex.quote(filename)}" if jq_pointer and filename else ""
    omitted = len(joined) - _MAX_OUTPUT_CHARS
    return joined[:_MAX_OUTPUT_CHARS] + f"\n… [{omitted:,} output chars truncated{hint}]"


_CELL_LABELS = {"markdown": "Markdown", "code": "Code", "raw": "Raw"}


def _extract_notebook(path: str, *, display_path: Optional[str] = None) -> str:
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            nb = json.load(fh)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ExtractionError(f"Not a valid notebook: {exc}") from exc
    if not isinstance(nb, dict):
        raise ExtractionError("Notebook root is not an object")
    raw_cells = nb.get("cells")
    if isinstance(raw_cells, list):
        cells = [(f".cells[{i}].outputs", cell) for i, cell in enumerate(raw_cells)]
    else:  # nbformat v3: cells live under worksheets
        cells = [
            (f".worksheets[{wi}].cells[{ci}].outputs", cell)
            for wi, ws in enumerate(nb.get("worksheets", [])) if isinstance(ws, dict)
            for ci, cell in enumerate(ws.get("cells", []))]
    if not cells:
        raise ExtractionError("Notebook contains no cells")
    # Backend bytes are parsed through a disposable host copy; recovery commands
    # must instead name the original notebook in the user's filesystem.
    nb_name = display_path if display_path is not None else path
    counts = dict.fromkeys(_CELL_LABELS, 0)
    out: list[str] = []
    for jq_pointer, cell in cells:
        typ = cell.get("cell_type") if isinstance(cell, dict) else None
        if typ not in _CELL_LABELS:
            continue
        counts[typ] += 1
        suffix = f" {counts[typ]}" if typ != "raw" else ""
        source = _source_text(cell.get("source", "")).rstrip("\n")
        out += [f"# ── {_CELL_LABELS[typ]} cell{suffix} ──", source, ""]
        rendered = _notebook_outputs(cell, jq_pointer, nb_name) if typ == "code" else ""
        if rendered:
            out += [f"# ── Output (cell {counts[typ]}) ──", rendered.rstrip("\n"), ""]
    return _joined(out, "Notebook contains no readable cells")


@contextlib.contextmanager
def _open_zip(path: str, kind: str) -> Iterator[zipfile.ZipFile]:
    """Open an OOXML package; bad-zip/OS failures (body included) become ExtractionError."""
    try:
        with zipfile.ZipFile(path) as zf:
            yield zf
    except (zipfile.BadZipFile, OSError) as exc:
        bad_zip = isinstance(exc, zipfile.BadZipFile)
        raise ExtractionError(f"Not a valid {kind}: {exc}" if bad_zip else str(exc)) from exc


def _zip_xml(zf: zipfile.ZipFile, name: str, optional: bool = False, *, max_bytes: Optional[int] = None,
             _charge: Optional[Callable[[int], None]] = None) -> Any:
    """Parse a package part; ``optional`` parts yield an empty element when absent or malformed."""
    try:
        if max_bytes is None:
            data = zf.read(name)
            if _charge is not None:
                _charge(len(data))
            return ET.fromstring(data)
        part = zf.getinfo(name)
        if part.file_size > max_bytes or part.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ExtractionError('Required document XML exceeds limit or uses unsupported compression')
        with zf.open(part) as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ExtractionError('Required document XML exceeds limit')
        if _charge is not None:
            _charge(len(data))
        return ET.fromstring(data)
    except (KeyError, ET.ParseError) as exc:
        if optional:
            return ET.Element("missing")
        raise ExtractionError(
            f"Missing {name}" if isinstance(exc, KeyError) else f"Malformed XML in {name}: {exc}"
        ) from exc


def _zip_part_bytes(zf: zipfile.ZipFile, name: str, max_bytes: int,
                    *, _charge: Optional[Callable[[int], None]] = None) -> bytes:
    """Bounded raw part bytes for parsers that map their own errors (e.g. sheet XML)."""
    part = zf.getinfo(name)
    if part.file_size > max_bytes or part.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ExtractionError('Required document XML exceeds limit or uses unsupported compression')
    with zf.open(part) as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ExtractionError('Required document XML exceeds limit')
    if _charge is not None:
        _charge(len(data))
    return data


def _extract_docx(path: str, *, max_xml_bytes: Optional[int] = None) -> str:
    with _open_zip(path, "DOCX") as zf:
        root = _zip_xml(zf, "word/document.xml", max_bytes=max_xml_bytes)
    w = f"{{{_NS_W}}}"
    breaks = {f"{w}tab": "\t", f"{w}br": "\n", f"{w}cr": "\n"}
    lines: list[str] = []
    for para in root.iter(f"{w}p"):
        # w:rt is the ruby (phonetic) guide over w:rubyBase; it annotates the text, it is not text.
        guide = {n for rt in para.iter(f"{w}rt") for n in rt.iter()}
        text = "".join(
            (n.text or "") if n.tag == f"{w}t" else breaks.get(n.tag, "")
            for n in para.iter() if n not in guide)
        lines.extend(text.split("\n"))
    return _joined(lines, "DOCX contains no extractable text")


def _xlsx_string_text(item: ET.Element, s: str) -> str:
    """Base text of an si/is, excluding rPh phonetic annotations."""
    return "".join(
        (child.text or "") if child.tag == f"{s}t" else child.findtext(f"{s}t") or ""
        for child in item if child.tag in {f"{s}t", f"{s}r"})


class _ScopedXlsxText(str):
    """Keep workbook evidence and its coverage on the existing document carrier."""
    def __new__(cls, text, *, inventory_included=True, formula_preview, structure_preview):
        result = super().__new__(cls, text)
        result.extraction_metadata = {
            "coverage": ("xlsx_workbook_inventory_and_visible_sheet_cell_value_preview" if inventory_included
                         else "xlsx_visible_sheet_cell_value_preview; workbook_inventory_omitted_size_limit")
                        + "; bounded_inert_formula_and_structure_previews; charts_comments_layout_not_inspected",
            "workbook_inventory": ("in_content; read_all_pages_for_complete_lists" if inventory_included
                                   else "omitted_size_limit; no_sheet_or_defined_name_inventory"),
            "cell_value_preview": {
                "sheets": "visible_only",
                "max_rows_per_sheet": _MAX_XLSX_ROWS_PER_SHEET,
                "max_columns": _MAX_XLSX_COLS,
                "hidden_rows_and_columns": "not_filtered",
                "formula_values": "saved_cache_only",
            },
            "formula_source_preview": formula_preview,
            "structure_preview": structure_preview,
            "recalculated": False,
            "filter_or_visibility_evaluated": False,
        }
        return result


def _xlsx_inventory(workbook: ET.Element, s: str) -> list[str]:
    """Enumerate actual workbook declarations, without inferring from history."""
    lines = ["# XLSX workbook inventory (xl/workbook.xml)",
             "Sheets (all declared sheets, including hidden; names and states only):"]
    lines.extend(json.dumps({"name": sheet.get("name", ""),
                             "state": sheet.get("state", "visible")}, ensure_ascii=False)
                 for sheet in workbook.findall(f"{s}sheets/{s}sheet"))
    lines.append("Defined names (all declarations; no inferred names):")
    defined = workbook.findall(f"{s}definedNames/{s}definedName")
    lines.extend(json.dumps({"name": item.get("name", ""),
                             "localSheetId": item.get("localSheetId")}, ensure_ascii=False)
                 for item in defined)
    if not defined:
        lines.append("(none)")
    lines += ["# End of workbook inventory",
              f"# Cell-value preview of visible sheets: at most {_MAX_XLSX_ROWS_PER_SHEET} rows "
              f"and {_MAX_XLSX_COLS} columns per sheet; hidden rows and columns are not filtered. "
              "Saved values only; no recalculation. "
              "Formula-source coverage is separately bounded; inspect extraction metadata. "
              "Charts, comments and layout are not inspected. "
              "Past descriptions or preservation results do not establish extra sheet/name declarations.", ""]
    return lines


class _XlsxFormulaPreview:
    """Bounded declarations from the same parsed preview cells, never a calculator."""
    def __init__(self):
        self.records = []
        self.bytes = 0
        self.observed = 0
        self.truncated = 0
        self.sheets = dict(parsed=0, skipped_hidden=0, skipped_missing_or_external=0,
                           skipped_malformed=0)
        self.rows_omitted = 0
        self.cells_omitted = 0
        self.structure_records = []
        self.structure_bytes = 0
        self.structure_observed = dict(hidden_row=0, hidden_column=0, auto_filter=0, merge=0)
        self.merge_rectangles = []
        self.merge_cells_listed = 0

    def _structure_add(self, kind, sheet, record):
        self.structure_observed[kind] += 1
        if len(self.structure_records) >= _MAX_XLSX_STRUCTURE_RECORDS:
            return
        line = json.dumps(dict(kind=kind, sheet=sheet, **record),
                          ensure_ascii=True, separators=(",", ":"))
        size = len(line.encode("utf-8")) + 1
        if size > _MAX_XLSX_STRUCTURE_RECORD_BYTES or self.structure_bytes + size > _MAX_XLSX_STRUCTURE_PREVIEW_BYTES:
            return
        self.structure_records.append(line)
        self.structure_bytes += size

    @staticmethod
    def _inert_filter_node(node, depth=0):
        if depth > 8:
            return {"truncated": "depth_limit"}
        text = node.text or ""
        children = list(node)
        return {
            "tag": node.tag.rsplit("}", 1)[-1],
            "attributes": dict(node.attrib),
            "text": text[:_MAX_XLSX_STRUCTURE_TEXT_CHARS],
            "text_truncated": len(text) > _MAX_XLSX_STRUCTURE_TEXT_CHARS,
            "children": [_XlsxFormulaPreview._inert_filter_node(child, depth + 1)
                         for child in children[:128]],
            "children_omitted": max(0, len(children) - 128),
        }

    @staticmethod
    def _structure_cell_ref(ref):
        match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})", ref or "")
        if match is None:
            raise ExtractionError("Invalid merged-cell reference")
        letters, raw_row = match.groups()
        col = 0
        for letter in letters.upper():
            col = col * 26 + ord(letter) - ord("A") + 1
        row = int(raw_row)
        if not 1 <= col <= 16384 or not 1 <= row <= 1048576:
            raise ExtractionError("Merged-cell reference outside XLSX bounds")
        return row, col

    @staticmethod
    def _structure_ref(row, col):
        letters = ""
        while col:
            col, remainder = divmod(col - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row}"

    def add_structure(self, root, sheet, shared, s):
        self.merge_rectangles = []
        for row in root.iter(f"{s}row"):
            hidden = row.get("hidden")
            if hidden is not None and hidden.lower() in {"1", "true"}:
                self._structure_add("hidden_row", sheet,
                                    {"row": row.get("r"), "hidden": hidden})
        for col in root.findall(f"{s}cols/{s}col"):
            hidden = col.get("hidden")
            if hidden is not None and hidden.lower() in {"1", "true"}:
                self._structure_add("hidden_column", sheet, {"attributes": dict(col.attrib)})
        for node in root.iter(f"{s}autoFilter"):
            self._structure_add("auto_filter", sheet, {
                "attributes": dict(node.attrib),
                "children": [self._inert_filter_node(child) for child in list(node)[:128]],
                "children_omitted": max(0, len(node) - 128),
                "evaluation": "not_evaluated; declarations only; no current visible subset inferred",
            })
        merges = root.findall(f"{s}mergeCells/{s}mergeCell")
        if len(merges) > _MAX_XLSX_MERGE_RANGES:
            raise ExtractionError("Too many merged-cell ranges")
        cells = {cell.get("r", "").upper(): cell for cell in root.iter(f"{s}c") if cell.get("r")}

        def stored(ref):
            cell = cells.get(ref)
            if cell is None:
                return {"cell": ref, "stored_state": "missing", "stored_value": None}
            value = _cell_value(cell, shared, s)
            return {"cell": ref, "stored_state": "blank" if not value else "present",
                    "stored_value": value, "formula_present": cell.find(f"{s}f") is not None}

        for merge in merges:
            raw_ref = merge.get("ref", "")
            parts = raw_ref.split(":")
            if len(parts) not in {1, 2}:
                raise ExtractionError("Invalid merged-cell range")
            start = self._structure_cell_ref(parts[0])
            end = self._structure_cell_ref(parts[-1])
            top, left = min(start[0], end[0]), min(start[1], end[1])
            bottom, right = max(start[0], end[0]), max(start[1], end[1])
            rectangle = (top, left, bottom, right)
            if any(top <= other[2] and bottom >= other[0]
                   and left <= other[3] and right >= other[1]
                   for other in self.merge_rectangles):
                raise ExtractionError("Overlapping merged-cell ranges")
            self.merge_rectangles.append(rectangle)
            anchor_ref = self._structure_ref(top, left)
            anchor = stored(anchor_ref)
            count = (bottom - top + 1) * (right - left + 1)
            nonanchors = []
            omitted = count - 1
            if count > 1 and count - 1 <= _MAX_XLSX_MERGE_CELLS - self.merge_cells_listed:
                for row in range(top, bottom + 1):
                    for col in range(left, right + 1):
                        ref = self._structure_ref(row, col)
                        if ref == anchor_ref:
                            continue
                        child = stored(ref)
                        child["inherited_display"] = {
                            "source_cell": anchor_ref, "value": anchor["stored_value"]}
                        nonanchors.append(child)
                self.merge_cells_listed += count - 1
                omitted = 0
            self._structure_add("merge", sheet, {
                "range": raw_ref, "anchor": anchor, "non_anchor_cells": nonanchors,
                "non_anchor_cells_omitted": omitted,
                "display_meaning": "declared merge anchor only; stored non-anchor blanks are not missing categories",
                "scope_limit": "no propagation outside this declared range; no formula evaluation",
            })

    def render_structure(self, available_bytes):
        header = ("\n# XLSX structure preview (inert JSON records; visible parsed sheets only)\n"
                  "# Hidden flags are declarations, not deletion or hiding causes. AutoFilter rules and "
                  "attributes are data, not evaluated verdicts or a current visible subset. Merged display "
                  "values come only from each declared anchor; non-anchor stored state remains explicit.\n")
        available_bytes = min(available_bytes, _MAX_XLSX_STRUCTURE_PREVIEW_BYTES)
        lines, used = [], len(header.encode("utf-8"))
        if used <= available_bytes:
            for line in self.structure_records:
                size = len(line.encode("utf-8")) + 1
                if used + size > available_bytes:
                    break
                lines.append(line)
                used += size
        observed = sum(self.structure_observed.values())
        metadata = dict(
            location="in_content; read_all_pages_for_available_records",
            scope="visible_parsed_sheets; declarations_not_filter_or_visibility_evaluation",
            observed_records=self.structure_observed,
            included_records=len(lines), omitted_records=observed - len(lines),
            max_records=_MAX_XLSX_STRUCTURE_RECORDS,
            max_record_bytes=_MAX_XLSX_STRUCTURE_RECORD_BYTES,
            max_preview_bytes=_MAX_XLSX_STRUCTURE_PREVIEW_BYTES,
            max_merge_ranges=_MAX_XLSX_MERGE_RANGES,
            max_materialized_non_anchor_cells=_MAX_XLSX_MERGE_CELLS,
            materialized_non_anchor_cells=self.merge_cells_listed,
            truncated=observed != len(lines), evaluated=False)
        if used > available_bytes:
            metadata["location"] = "omitted_size_limit"
            return "", metadata
        return header + "".join(line + "\n" for line in lines), metadata

    def add(self, sheet, cell, s):
        formula = cell.find(f"{s}f")
        if formula is None:
            return
        self.observed += 1
        if len(self.records) >= _MAX_XLSX_FORMULA_RECORDS:
            return
        value = cell.find(f"{s}v")
        source = formula.text or ""
        cache = None if value is None else (value.text or "")
        truncated = [key for key, text in (("formula", source), ("saved_cache.raw_value", cache))
                     if text is not None and len(text) > _MAX_XLSX_FORMULA_TEXT_CHARS]
        record = dict(sheet=sheet, cell=cell.get("r"),
                      formula=source[:_MAX_XLSX_FORMULA_TEXT_CHARS],
                      formula_attributes=dict(formula.attrib),
                      saved_cache=dict(state="missing" if value is None else
                                       "blank" if not cache else "present",
                                       cell_type=cell.get("t", "n"),
                                       raw_value=None if cache is None else cache[:_MAX_XLSX_FORMULA_TEXT_CHARS]),
                      truncated_fields=truncated)
        # JSON escapes newlines, controls and non-ASCII. Source is inert text;
        # shared/array attributes are retained exactly, without reconstruction.
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        size = len(line.encode("utf-8")) + 1
        if size > _MAX_XLSX_FORMULA_RECORD_BYTES or self.bytes + size > _MAX_XLSX_FORMULA_PREVIEW_BYTES:
            return
        self.records.append((line, bool(truncated)))
        self.bytes += size

    def render(self, available_bytes):
        header = ("\n# XLSX formula source preview (inert JSON records; visible preview cells only)\n"
                  "# Saved caches only; missing/blank caches are not formula results. No evaluation, "
                  "recalculation or shared/array reconstruction; not a full-workbook formula inventory.\n")
        available_bytes = min(available_bytes, _MAX_XLSX_FORMULA_PREVIEW_BYTES)
        lines, used = [], len(header.encode("utf-8"))
        if used <= available_bytes:
            for line, truncated in self.records:
                size = len(line.encode("utf-8")) + 1
                if used + size > available_bytes:
                    break
                lines.append(line)
                self.truncated += truncated
                used += size
        metadata = dict(location="in_content; read_all_pages_for_available_records",
                        scope="visible_sheet_cell_preview_only; not_full_workbook_formula_inventory",
                        max_row_elements_per_sheet=_MAX_XLSX_ROWS_PER_SHEET,
                        max_columns=_MAX_XLSX_COLS, hidden_rows_and_columns="not_filtered",
                        max_records=_MAX_XLSX_FORMULA_RECORDS,
                        max_text_chars=_MAX_XLSX_FORMULA_TEXT_CHARS,
                        max_record_bytes=_MAX_XLSX_FORMULA_RECORD_BYTES,
                        max_preview_bytes=_MAX_XLSX_FORMULA_PREVIEW_BYTES,
                        observed_formula_cells=self.observed, included_records=len(lines),
                        omitted_records=self.observed-len(lines),
                        records_with_truncated_fields=self.truncated,
                        truncated=bool(self.observed-len(lines) or self.truncated),
                        sheets=self.sheets, rows_omitted_by_preview_limit=self.rows_omitted,
                        cells_omitted_by_column_limit=self.cells_omitted,
                        shared_and_array_formulas="attributes_only; no_reconstruction",
                        saved_cache_only=True, evaluated=False)
        if used > available_bytes:
            metadata["location"] = "omitted_size_limit"
            return "", metadata
        return header + "".join(line + "\n" for line in lines), metadata


def _extract_xlsx(path: str, *, max_xml_bytes: Optional[int] = None,
                  max_total_xml_bytes: Optional[int] = None, include_inventory: bool = False) -> str:
    s, r, pr = f"{{{_NS_S}}}", f"{{{_NS_REL}}}", f"{{{_NS_PKG_REL}}}"
    with _open_zip(path, "XLSX") as zf:
        names = set(zf.namelist())
        # Aggregate bound (bounded lanes only): actual uncompressed bytes of every required
        # part read are charged, so repeated sheet references and many individually small
        # parts cannot multiply work past max_total_xml_bytes. Abort fires before the part
        # that would cross the budget is parsed; at most one extra per-part-bounded read
        # is charged past the budget. Generic callers (max_xml_bytes=None) never charge.
        spent = 0

        def _charge(n_bytes: int) -> None:
            nonlocal spent
            spent += n_bytes
            if max_total_xml_bytes is not None and spent > max_total_xml_bytes:
                raise ExtractionError('Required document XML aggregate exceeds limit')

        charge = _charge if max_xml_bytes is not None else None
        sst = _zip_xml(zf, "xl/sharedStrings.xml", optional=True, max_bytes=max_xml_bytes, _charge=charge)
        shared = [_xlsx_string_text(item, s) for item in sst.iter(f"{s}si")]
        rels_root = _zip_xml(zf, "xl/_rels/workbook.xml.rels", optional=True, max_bytes=max_xml_bytes, _charge=charge)
        rels = {rel.get("Id", ""): rel.get("Target", "")
                for rel in rels_root.iter(f"{pr}Relationship")
                if rel.get("Id") and (max_xml_bytes is None or rel.get("TargetMode") != "External")}
        workbook = _zip_xml(zf, "xl/workbook.xml", max_bytes=max_xml_bytes, _charge=charge)
        out: list[str] = []
        formulas = _XlsxFormulaPreview() if include_inventory else None
        for sheet in workbook.iter(f"{s}sheet"):
            target = rels.get(sheet.get(f"{r}id", ""), "").lstrip("/")
            part = posixpath.normpath(target if target.startswith("xl/") else f"xl/{target}")
            if sheet.get("state", "visible") in {"hidden", "veryHidden"}:
                if formulas is not None:
                    formulas.sheets["skipped_hidden"] += 1
                continue
            if part not in names:
                if formulas is not None:
                    formulas.sheets["skipped_missing_or_external"] += 1
                continue
            try:
                rows = _sheet_rows(
                    _zip_part_bytes(zf, part, max_xml_bytes, _charge=charge) if max_xml_bytes is not None
                    else zf.read(part), shared, formulas=formulas, sheet=sheet.get('name', 'Sheet'))
                if formulas is not None:
                    formulas.sheets["parsed"] += 1
                out += [f"# ── Sheet: {sheet.get('name', 'Sheet')} ──",
                        *(["\t".join(row) for row in rows] or ["(empty)"]), ""]
            except ET.ParseError:
                if formulas is not None:
                    formulas.sheets["skipped_malformed"] += 1
    text = _joined(out, "XLSX has no visible sheets with content")
    if include_inventory:
        augmented = "\n".join(_xlsx_inventory(workbook, s)) + text
        # The scoped lane already caps extracted text at 1 MB. Preserve an
        # otherwise readable preview if optional inventory would cross it.
        inventory_included = len(augmented.encode("utf-8")) <= 1000000
        if inventory_included:
            text = augmented
        formula_text, metadata = formulas.render(1000000-len(text.encode("utf-8")))
        combined = text + formula_text
        structure_text, structure_metadata = formulas.render_structure(
            1000000-len(combined.encode("utf-8")))
        return _ScopedXlsxText(combined + structure_text, inventory_included=inventory_included,
                               formula_preview=metadata, structure_preview=structure_metadata)
    return text


def _col_index(ref: str) -> int:
    """0-based column of a cell ref: ``A1`` -> 0, ``AB7`` -> 27 (bijective base-26 letters)."""
    idx = functools.reduce(lambda acc, ch: acc * 26 + ord(ch.upper()) - ord("A") + 1,
                           itertools.takewhile(str.isalpha, ref), 0)
    return max(idx - 1, 0)


def _sheet_rows(xml_bytes: bytes, shared: list[str], *, formulas=None, sheet=None) -> list[list[str]]:
    root = ET.fromstring(xml_bytes)
    s = f"{{{_NS_S}}}"
    if formulas is not None:
        formulas.add_structure(root, sheet, shared, s)
    rows: list[list[str]] = []
    for index, row in enumerate(root.iter(f"{s}row")):
        if index >= _MAX_XLSX_ROWS_PER_SHEET:
            if formulas is None:
                break
            formulas.rows_omitted += 1
            continue
        cells: dict[int, str] = {}
        max_col = -1
        for cell in row.iter(f"{s}c"):
            col = _col_index(cell.get("r", "")) if cell.get("r") else max_col + 1
            if col < _MAX_XLSX_COLS:
                if formulas is not None:
                    formulas.add(sheet, cell, s)
                # Missing/blank formula caches are not FALSE or #ERROR results.
                no_cache = (formulas is not None and cell.find(f"{s}f") is not None
                            and not cell.findtext(f"{s}v"))
                cells[col] = "" if no_cache else _cell_value(cell, shared, s)
                max_col = max(max_col, col)
            elif formulas is not None:
                formulas.cells_omitted += 1
        rows.append([cells.get(i, "") for i in range(max_col + 1)])
    while rows and not any(value.strip() for value in rows[-1]):
        rows.pop()
    return rows


def _cell_value(cell: ET.Element, shared: list[str], s: str) -> str:
    value = cell.findtext(f"{s}v") or ""
    typ = cell.get("t", "")
    if typ == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            return ""
    if typ == "inlineStr":
        inline = cell.find(f"{s}is")
        return "" if inline is None else _xlsx_string_text(inline, s)
    if typ == "b":
        return "TRUE" if value.strip() in {"1", "true", "TRUE"} else "FALSE"
    return (value or "#ERROR") if typ == "e" else value


_SQLITE_MAGIC = b"SQLite format 3\x00"
_SQLITE_PREVIEW_ROWS = 5
_SQLITE_MAX_TABLES = 200
_SQLITE_CELL_CHARS = 80


def _extract_sqlite(path: str) -> str:
    """Render a SQLite file as a schema overview: per table the CREATE statement, row count and the
    first rows. A ``.db`` that is not SQLite raises ExtractionError so read_file reports the real type."""
    import sqlite3

    with open(path, "rb") as fh:
        if fh.read(len(_SQLITE_MAGIC)) != _SQLITE_MAGIC:
            raise ExtractionError("not a SQLite database (magic bytes do not match)")
    # Read-only URI: never create or mutate; immutable=1 also skips WAL/journal sidecars so a live
    # database that another process has open is still readable without taking locks.
    uri = Path(path).resolve().as_uri() + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    try:
        objs = con.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC, name"
        ).fetchall()
        out = ["# SQLite database", ""]
        tables = [o for o in objs if o[0] == "table"]
        others = [o for o in objs if o[0] != "table"]
        out.append(f"{len(tables)} table(s), {len(others)} index/view/trigger(s)")
        for _, name, sql in tables[:_SQLITE_MAX_TABLES]:
            quoted = '"' + name.replace('"', '""') + '"'
            count = con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            out += ["", f"## {name}  ({count:,} rows)", sql.strip()]
            cur = con.execute(f"SELECT * FROM {quoted} LIMIT {_SQLITE_PREVIEW_ROWS}")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            if rows:
                out.append("| " + " | ".join(cols) + " |")
                out.append("|" + "---|" * len(cols))
                for row in rows:
                    cells = [_sqlite_cell(v) for v in row]
                    out.append("| " + " | ".join(cells) + " |")
        if len(tables) > _SQLITE_MAX_TABLES:
            out.append(f"\n... {len(tables) - _SQLITE_MAX_TABLES} more tables omitted")
        if others:
            out += ["", "## Indexes / views / triggers"] + [f"- {t} {n}" for t, n, _ in others]
        out += ["", "Query it with the terminal: sqlite3 <path> 'SELECT ...'  (or Python's sqlite3 module)."]
        return "\n".join(out)
    except sqlite3.DatabaseError as exc:
        raise ExtractionError(f"SQLite read failed: {exc}") from exc
    finally:
        con.close()


def _sqlite_cell(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (bytes, bytearray)):
        return f"<blob {len(value)} bytes>"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= _SQLITE_CELL_CHARS else text[:_SQLITE_CELL_CHARS - 1] + "…"


# Extension -> stdlib extractor; anydoc formats fall through in extract_document_text.
_STDLIB_EXTRACTORS: dict[str, Callable[[str], str]] = {
    ".ipynb": _extract_notebook, ".docx": _extract_docx, ".xlsx": _extract_xlsx,
    ".db": _extract_sqlite, ".sqlite": _extract_sqlite, ".sqlite3": _extract_sqlite}
