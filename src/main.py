from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from openpyxl import Workbook

from .config import REQUIRED_FIELDS
from .llm import extract_structured
from .pdf_extract import extract_text_pages


def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
        return
    except Exception:
        pass

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _iter_pdfs(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*.pdf"))


def _chunk_pages_by_count(pages: list[str], chunk_pages: int | None) -> list[str]:
    if not pages:
        return []

    if not chunk_pages or chunk_pages <= 0:
        return ["\n".join(pages)]

    chunks: list[str] = []
    for i in range(0, len(pages), chunk_pages):
        chunk = [p for p in pages[i : i + chunk_pages] if p]
        if chunk:
            chunks.append("\n".join(chunk))
    return chunks


def _chunk_pages_by_chars(pages: list[str], max_chars: int | None) -> list[str]:
    if not pages:
        return []

    if not max_chars or max_chars <= 0:
        return ["\n".join(pages)]

    chunks: list[str] = []
    buffer: list[str] = []
    current = 0

    for page in pages:
        if not page:
            continue
        page_len = len(page) + 1
        if buffer and current + page_len > max_chars:
            chunks.append("\n".join(buffer))
            buffer = [page]
            current = page_len
        else:
            buffer.append(page)
            current += page_len

    if buffer:
        chunks.append("\n".join(buffer))

    return chunks


def _merge_schema(base: list[str], new: list[str]) -> list[str]:
    merged = list(base)
    for field in new:
        if field not in merged:
            merged.append(field)

    for required in reversed(REQUIRED_FIELDS):
        if required in merged:
            merged.remove(required)
        merged.insert(0, required)

    return merged


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _load_cached_chunk(path: Path) -> tuple[list[str], list[dict]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    schema = data.get("schema")
    records = data.get("records")
    if not isinstance(schema, list) or not isinstance(records, list):
        return None
    return schema, records


def _save_cached_chunk(path: Path, schema: list[str], records: list[dict]) -> None:
    payload = {"schema": schema, "records": records}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_excel(path: Path, header: list[str], records: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    ws.append(header)

    for record in records:
        ws.append([record.get(field, "") for field in header])

    wb.save(path)


def _render_progress(current: int, total: int, status: str) -> None:
    if total <= 0:
        return
    width = 30
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r  [{bar}] {current}/{total} {status}", end="", flush=True)


def main() -> None:
    _load_env()

    root = Path(__file__).resolve().parents[1]
    input_dir = root / "input"
    output_dir = root / "output"
    output_dir.mkdir(exist_ok=True)

    max_pages_raw = os.getenv("MAX_PAGES")
    max_pages = int(max_pages_raw) if max_pages_raw else None
    max_chars_raw = os.getenv("MAX_CHARS_PER_CHUNK")
    max_chars = int(max_chars_raw) if max_chars_raw else None
    chunk_pages_raw = os.getenv("CHUNK_PAGES")
    chunk_pages = int(chunk_pages_raw) if chunk_pages_raw else None
    cache_reset = _truthy(os.getenv("CACHE_RESET"))

    cache_root = root / "cache"
    cache_root.mkdir(exist_ok=True)

    for pdf_path in _iter_pdfs(input_dir):
        pages = extract_text_pages(pdf_path, max_pages=max_pages)
        if not pages:
            continue
        print(f"Extracted {len(pages)} text page(s) from {pdf_path.name}")

        if chunk_pages:
            chunks = _chunk_pages_by_count(pages, chunk_pages)
        else:
            chunks = _chunk_pages_by_chars(pages, max_chars)

        pdf_cache_dir = cache_root / pdf_path.stem
        if cache_reset and pdf_cache_dir.exists():
            shutil.rmtree(pdf_cache_dir)
        pdf_cache_dir.mkdir(exist_ok=True)

        chunk_results: list[tuple[list[str], list[dict]]] = []
        total_chunks = len(chunks)
        print(f"Processing {pdf_path.name}: {total_chunks} chunk(s)")

        for idx, chunk in enumerate(chunks, start=1):
            cache_path = pdf_cache_dir / f"chunk_{idx}.json"
            cached = _load_cached_chunk(cache_path)
            if cached is None:
                _render_progress(idx, total_chunks, "running")
                schema, chunk_records = extract_structured(chunk, source_name=pdf_path.name)
                _save_cached_chunk(cache_path, schema, chunk_records)
                chunk_results.append((schema, chunk_records))
            else:
                _render_progress(idx, total_chunks, "cached")
                chunk_results.append(cached)
        if total_chunks > 0:
            print()

        merged_schema: list[str] = []
        records: list[dict] = []

        for schema, chunk_records in chunk_results:
            merged_schema = _merge_schema(merged_schema, schema)

            for record in chunk_records:
                record["record_index"] = len(records) + 1
                records.append(record)

        for record in records:
            for field in merged_schema:
                record.setdefault(field, "")

        out_json = output_dir / f"{pdf_path.stem}.json"
        out_json.write_text(
            json.dumps({"schema": merged_schema, "records": records}, indent=2),
            encoding="utf-8",
        )

        out_xlsx = output_dir / f"{pdf_path.stem}.xlsx"
        _write_excel(out_xlsx, merged_schema, records)

        print(f"Completed {pdf_path.name}: {len(records)} record(s)")


if __name__ == "__main__":
    main()
