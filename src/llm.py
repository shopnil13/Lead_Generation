from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import (
    DROP_FIELDS,
    REQUIRED_FIELDS,
    REPAIR_SYSTEM_PROMPT,
    REPAIR_USER_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


@dataclass
class LlmConfig:
    provider: str
    temperature: float
    request_timeout: float
    retries: int
    retry_backoff: float
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"


class LlmError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise LlmError("LLM response did not contain JSON")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LlmError(f"Invalid JSON in LLM response: {exc}") from exc


def _normalize_field(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _normalize_response(data: Any, source_name: str) -> tuple[list[str], list[dict]]:
    if isinstance(data, list):
        records = data
        schema = []
    elif isinstance(data, dict) and "records" in data:
        records = data.get("records") or []
        schema = data.get("schema") or []
    elif isinstance(data, dict):
        records = [data]
        schema = list(data.keys())
    else:
        raise LlmError("Unexpected JSON shape from LLM")

    if not isinstance(records, list):
        raise LlmError("'records' must be a list")

    normalized_schema: list[str] = []
    drop_set = {name.strip().lower() for name in DROP_FIELDS}

    for field in schema:
        if not isinstance(field, str):
            continue
        nf = _normalize_field(field)
        if nf in drop_set:
            continue
        if nf and nf not in normalized_schema:
            normalized_schema.append(nf)

    for req in REQUIRED_FIELDS:
        if req not in normalized_schema:
            normalized_schema.insert(0, req)

    normalized_records: list[dict] = []
    for idx, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        normalized_record: dict[str, Any] = {}
        for key, value in record.items():
            if not isinstance(key, str):
                continue
            nk = _normalize_field(key)
            if not nk or nk in drop_set:
                continue
            normalized_record[nk] = "" if value is None else value

        normalized_record.setdefault("record_index", idx)

        for field in normalized_schema:
            normalized_record.setdefault(field, "")

        normalized_records.append(normalized_record)

    return normalized_schema, normalized_records


def _session_with_retries(cfg: LlmConfig) -> requests.Session:
    retry = Retry(
        total=cfg.retries,
        backoff_factor=cfg.retry_backoff,
        status_forcelist=[408, 429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _call_openai_raw(prompt: str, cfg: LlmConfig, system_prompt: str) -> str:
    if not cfg.openai_api_key or not cfg.openai_model:
        raise LlmError("Missing OPENAI_API_KEY or OPENAI_MODEL")

    url = f"{cfg.openai_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.openai_model,
        "temperature": cfg.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    session = _session_with_retries(cfg)
    resp = session.post(url, headers=headers, json=payload, timeout=cfg.request_timeout)
    if resp.status_code >= 400:
        raise LlmError(f"OpenAI error {resp.status_code}: {resp.text}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_gemini_raw(prompt: str, cfg: LlmConfig, system_prompt: str) -> str:
    if not cfg.gemini_api_key or not cfg.gemini_model:
        raise LlmError("Missing GEMINI_API_KEY or GEMINI_MODEL")

    url = f"{cfg.gemini_api_base}/models/{cfg.gemini_model}:generateContent"
    params = {"key": cfg.gemini_api_key}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{prompt}"}],
            }
        ],
        "generationConfig": {"temperature": cfg.temperature},
    }
    session = _session_with_retries(cfg)
    resp = session.post(url, params=params, json=payload, timeout=cfg.request_timeout)
    if resp.status_code >= 400:
        raise LlmError(f"Gemini error {resp.status_code}: {resp.text}")

    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _repair_json(bad_json: str, cfg: LlmConfig) -> dict:
    repair_prompt = REPAIR_USER_PROMPT_TEMPLATE.format(bad_json=bad_json)
    if cfg.provider == "openai":
        content = _call_openai_raw(repair_prompt, cfg, REPAIR_SYSTEM_PROMPT)
    elif cfg.provider == "gemini":
        content = _call_gemini_raw(repair_prompt, cfg, REPAIR_SYSTEM_PROMPT)
    else:
        raise LlmError(f"Unsupported LLM_PROVIDER: {cfg.provider}")

    return _extract_json(content)


def extract_structured(text: str, source_name: str) -> tuple[list[str], list[dict]]:
    required_fields = ", ".join(REQUIRED_FIELDS)
    prompt = USER_PROMPT_TEMPLATE.format(
        required_fields=required_fields,
        name=source_name,
        text=text,
    )

    cfg = LlmConfig(
        provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0") or "0"),
        request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "120") or "120"),
        retries=int(os.getenv("LLM_RETRIES", "2") or "2"),
        retry_backoff=float(os.getenv("LLM_RETRY_BACKOFF", "1.5") or "1.5"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL"),
        openai_api_base=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL"),
        gemini_api_base=os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"),
    )

    if cfg.provider == "openai":
        content = _call_openai_raw(prompt, cfg, SYSTEM_PROMPT)
    elif cfg.provider == "gemini":
        content = _call_gemini_raw(prompt, cfg, SYSTEM_PROMPT)
    else:
        raise LlmError(f"Unsupported LLM_PROVIDER: {cfg.provider}")

    try:
        data = _extract_json(content)
    except LlmError:
        data = _repair_json(content, cfg)

    return _normalize_response(data, source_name)
