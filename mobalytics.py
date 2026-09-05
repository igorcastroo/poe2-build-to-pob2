"""Import public PoE2 guide variants through Mobalytics' Build Planner export."""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests
from converter import MAX_INPUT, validate_source

MAX_PAGE = 8 * 1024 * 1024
MOBALYTICS_HOSTS = {"mobalytics.gg", "www.mobalytics.gg"}
DOCUMENT_ID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I)
EXPORT_QUERY = """query Poe2UgDocumentWidgetBuildPlannerExportQuery($input: Poe2UserGeneratedDocumentInputById!, $variantId: String!) {
  poe2 {
    documents {
      userGeneratedDocumentById(input: $input) {
        error
        errorMessage
        data { exportToGame(variantId: $variantId) }
      }
    }
  }
}"""


class MobalyticsImportError(ValueError):
    """The URL could not be safely imported as public PoE2 build data."""


@dataclass(frozen=True)
class ImportResult:
    guide_name: str
    files: list[Path]
    rejected: list[str]


def validate_guide_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or parsed.hostname not in MOBALYTICS_HOSTS
            or not parsed.path.startswith("/poe-2/builds/")):
        raise MobalyticsImportError("Use a public https://mobalytics.gg/poe-2/builds/... link")
    return parsed.geturl()


def _client():
    return requests.Session(impersonate="chrome")


def _json_response(response, context: str):
    if response.status_code != 200:
        raise MobalyticsImportError(f"Mobalytics returned HTTP {response.status_code} while {context}")
    if len(response.content) > MAX_PAGE:
        raise MobalyticsImportError(f"Mobalytics response is too large while {context}")
    try:
        return response.json()
    except ValueError as exc:
        raise MobalyticsImportError(f"Mobalytics returned invalid JSON while {context}") from exc


def _preloaded_state(html: str):
    marker = "window.__PRELOADED_STATE__="
    start = html.find(marker)
    if start < 0:
        raise MobalyticsImportError("This page does not expose Mobalytics build data")
    start += len(marker)
    end = html.find("</script>", start)
    raw = html[start:end].rstrip().rstrip(";") if end >= 0 else ""
    if not raw or len(raw.encode("utf-8")) > MAX_PAGE:
        raise MobalyticsImportError("Mobalytics build data is missing or too large")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MobalyticsImportError("Mobalytics build data is malformed") from exc


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _document_id(state) -> str:
    for value in _walk(state):
        identifier = value.get("id") if isinstance(value, dict) else None
        if (isinstance(identifier, str) and DOCUMENT_ID.fullmatch(identifier)
                and value.get("type") == "builds"):
            return identifier
    raise MobalyticsImportError("Could not find this guide's public document ID")


def _variant_ids(state) -> list[str]:
    for value in _walk(state):
        variants = value.get("buildVariants") if isinstance(value, dict) else None
        rows = variants.get("values") if isinstance(variants, dict) else None
        if isinstance(rows, list):
            result = [row.get("id") for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]
            if result and len(result) == len(set(result)):
                return result
    raise MobalyticsImportError("This guide has no exportable build variants")


def _variant_names(html: str, ids: set[str]) -> dict[str, str]:
    """Read the labels presented by the guide, without guessing from file names."""
    pattern = re.compile(r'<div[^>]*data-key="([^"]+)"[^>]*>.*?<span[^>]*>(.*?)</span>', re.S)
    names = {}
    for identifier, label in pattern.findall(html):
        label = unescape(re.sub(r'<[^>]*>', '', label)).strip()
        if identifier in ids and label:
            names.setdefault(identifier, label)
    return names


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value).strip().rstrip(".")
    return (value[:140] or fallback).strip()


def _export_variant(session, url: str, document_id: str, variant_id: str):
    payload = {
        "query": EXPORT_QUERY,
        "variables": {"input": {"id": document_id}, "variantId": variant_id},
        "operationName": "Poe2UgDocumentWidgetBuildPlannerExportQuery",
    }
    response = session.post(
        "https://mobalytics.gg/api/poe-2/v1/graphql/query", json=payload,
        headers={"Origin": "https://mobalytics.gg", "Referer": url}, timeout=30,
    )
    body = _json_response(response, f"exporting variant {variant_id}")
    try:
        exported = body["data"]["poe2"]["documents"]["userGeneratedDocumentById"]
        text = exported["data"]["exportToGame"]
        if exported.get("error") or not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT:
            raise KeyError
        data = json.loads(text)
        validate_source(data)
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise MobalyticsImportError(f"Variant {variant_id} did not return a valid .build file") from exc
    return data, text


def import_guide(url: str, destination: str | Path) -> ImportResult:
    """Fetch every public guide variant and save only validated official .build files."""
    url = validate_guide_url(url)
    session = _client()
    response = session.get(url, timeout=30)
    if response.status_code != 200:
        raise MobalyticsImportError(f"Mobalytics returned HTTP {response.status_code} while opening the guide")
    if len(response.content) > MAX_PAGE:
        raise MobalyticsImportError("Mobalytics guide page is too large")
    state = _preloaded_state(response.text)
    document_id, variant_ids = _document_id(state), _variant_ids(state)
    variant_names = _variant_names(response.text, set(variant_ids))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    files, rejected, used_names = [], [], set()
    for variant_id in variant_ids:
        try:
            data, text = _export_variant(session, url, document_id, variant_id)
            name = _safe_name(variant_names.get(variant_id, data.get("name", "")), f"Variant {variant_id}")
            candidate, suffix = name, 2
            while candidate.casefold() in used_names:
                candidate = f"{name} ({suffix})"
                suffix += 1
            used_names.add(candidate.casefold())
            path = destination / f"{candidate}.build"
            path.write_text(text, encoding="utf-8", newline="\n")
            files.append(path)
        except (OSError, MobalyticsImportError) as exc:
            rejected.append(f"Variant {variant_id}: {exc}")
    if not files:
        detail = "; ".join(rejected) or "no variants returned"
        raise MobalyticsImportError(f"No valid .build files were imported: {detail}")
    guide_name = next((value.get("name") for value in _walk(state)
                       if isinstance(value.get("name"), str) and value.get("buildVariants")), "Mobalytics guide")
    return ImportResult(guide_name, files, rejected)
