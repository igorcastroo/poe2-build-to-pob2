"""Import public PoE2 guide variants through Mobalytics' Build Planner export."""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
import re
import zlib
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
import xml.etree.ElementTree as ET

from curl_cffi import requests
from converter import MAX_INPUT, decode, validate_source

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
    quest_rewards: int
    pob_code: str | None = None
    active_file: Path | None = None


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


def _pob2_code(state, html: str) -> str | None:
    """Return an embedded, already-valid PoB2 import code when a guide has one."""
    candidates = []
    if state is not None:
        for row in _walk(state):
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                key = str(key).casefold()
                if isinstance(value, str) and ('pob' in key or 'pathofbuilding' in key):
                    candidates.append(value)
    # A guide author can place a code directly in article HTML rather than state.
    candidates.extend(re.findall(r'(?<![A-Za-z0-9_+/=-])([A-Za-z0-9_+/=-]{40,})(?![A-Za-z0-9_+/=-])', unescape(html)))
    for candidate in candidates:
        code = ''.join(candidate.split())
        if len(code) > MAX_INPUT * 2:
            continue
        try:
            decode_pob2_code(code)
        except (ValueError, OSError, zlib.error):
            continue
        return code
    return None


def decode_pob2_code(code: str) -> bytes:
    """Decode a published code without imposing converter-specific set rules."""
    xml = decode(code)
    root = ET.fromstring(xml)
    if root.tag != 'PathOfBuilding2':
        raise ValueError('Embedded code is not a Path of Building 2 build')
    return xml


def _guide_name(state, html: str) -> str:
    if state is not None:
        name = next((value.get("name") for value in _walk(state)
                     if isinstance(value.get("name"), str) and value.get("buildVariants")), None)
        if name:
            return name
    title = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
    return unescape(re.sub(r'<[^>]*>', '', title.group(1))).strip() if title else "Mobalytics guide"


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


def _active_variant_id(url: str) -> str | None:
    """Read Mobalytics' public activeVariantId query value, when supplied."""
    for _, value in parse_qsl(urlparse(url).query, keep_blank_values=True):
        match = re.search(r'(?:^|,)activeVariantId,([0-9a-f-]{36})(?:,|$)', value, re.I)
        if match and DOCUMENT_ID.fullmatch(match.group(1)):
            return match.group(1)
    return None


def _guide_quest_rewards(state) -> list[dict]:
    """Keep the guide's explicit reward choices as local .build metadata."""
    for value in _walk(state):
        raw = value.get("questRewards") if isinstance(value, dict) else None
        rows = raw.get("quests") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            continue
        result = []
        for row in rows:
            quest = row.get("quest") if isinstance(row, dict) else None
            reward = row.get("reward") if isinstance(row, dict) else None
            if not isinstance(quest, dict) or not isinstance(reward, dict):
                continue
            quest_values = {key: quest.get(key) for key in ("slug", "name", "act", "area")}
            modifiers = reward.get("modifiers")
            reward_values = {key: reward.get(key) for key in ("slug", "name", "bakedDescription")}
            if (not all(isinstance(item, str) and item for item in quest_values.values())
                    or not all(isinstance(item, str) and item for item in reward_values.values())
                    or not isinstance(modifiers, list)
                    or not modifiers or not all(isinstance(item, str) and item for item in modifiers)):
                continue
            reward_values["modifiers"] = modifiers
            result.append({"quest": quest_values, "reward": reward_values})
        return result
    return []


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
    """Fetch public variants and retain explicit guide reward choices locally."""
    url = validate_guide_url(url)
    session = _client()
    response = session.get(url, timeout=30)
    if response.status_code != 200:
        raise MobalyticsImportError(f"Mobalytics returned HTTP {response.status_code} while opening the guide")
    if len(response.content) > MAX_PAGE:
        raise MobalyticsImportError("Mobalytics guide page is too large")
    try:
        state = _preloaded_state(response.text)
    except MobalyticsImportError:
        code = _pob2_code(None, response.text)
        if not code:
            raise
        return ImportResult(_guide_name(None, response.text), [], [], 0, code)
    code = _pob2_code(state, response.text)
    if code:
        return ImportResult(_guide_name(state, response.text), [], [], 0, code)
    document_id, variant_ids = _document_id(state), _variant_ids(state)
    active_variant_id = _active_variant_id(url)
    variant_names = _variant_names(response.text, set(variant_ids))
    quest_rewards = _guide_quest_rewards(state)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    files, rejected, used_names, active_file = [], [], set(), None
    for variant_id in variant_ids:
        try:
            data, text = _export_variant(session, url, document_id, variant_id)
            if quest_rewards:
                data["poe2_build_to_pob2"] = {
                    "source": {"provider": "Mobalytics", "guide_url": url},
                    "quest_rewards": quest_rewards,
                }
                validate_source(data)
                text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
            name = _safe_name(variant_names.get(variant_id, data.get("name", "")), f"Variant {variant_id}")
            candidate, suffix = name, 2
            while candidate.casefold() in used_names:
                candidate = f"{name} ({suffix})"
                suffix += 1
            used_names.add(candidate.casefold())
            path = destination / f"{candidate}.build"
            path.write_text(text, encoding="utf-8", newline="\n")
            files.append(path)
            if variant_id == active_variant_id:
                active_file = path
        except (OSError, MobalyticsImportError) as exc:
            rejected.append(f"Variant {variant_id}: {exc}")
    if not files:
        detail = "; ".join(rejected) or "no variants returned"
        raise MobalyticsImportError(f"No valid .build files were imported: {detail}")
    return ImportResult(_guide_name(state, response.text), files, rejected, len(quest_rewards), active_file=active_file)
