"""Outils autonomes exécutés par la boucle ReAct locale de Hermes Agent.

Fournit trois outils structurés compatibles OpenAI/OpenRouter `tools` :
- `web_search` : recherche multi-moteurs via SearXNG (`providers.search_web`).
- `fetch_url` : lecture sécurisée (anti-SSRF) d'une page web via `web.fetch_and_parse_web_url`.
- `github_inspect` : interrogation structurée de l'API REST GitHub (dépôt, 5 derniers commits,
  3 dernières releases, langages) afin d'obtenir des dates, hashes et URLs vérifiables.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from . import providers, web
from .config import Settings
from .tool_registry import CLAIR_TOOL_REGISTRY, ToolExecutionContext, permissions_from_enabled_tools

_GITHUB_TIMEOUT = httpx.Timeout(12.0, connect=5.0, pool=5.0)
_GITHUB_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_MAX_FETCH_CHARS = 6000


def build_openai_tools(enabled_tools: list[str], web_search_enabled: bool) -> list[dict[str, Any]]:
    """Construit la liste des schémas d'outils OpenAI/OpenRouter selon les outils activés."""
    tools: list[dict[str, Any]] = []
    if "web_search" in enabled_tools:
        if web_search_enabled:
            tools.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Recherche des pages web récentes via SearXNG. Utilise des requêtes courtes "
                        "et précises ; tu peux enchaîner plusieurs requêtes si nécessaire."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Requête de recherche ciblée."},
                            "limit": {
                                "type": "integer",
                                "description": "Nombre de résultats (entre 1 et 8, défaut 5).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )

    tools.extend(
        [
            {
                "type": "function",
                "function": {
                    "name": "fetch_url",
                    "description": (
                        "Lit le contenu textuel d'une URL publique HTTP/HTTPS (page officielle, "
                        "documentation, README) pour vérifier des faits précis."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL publique complète (https://...)."},
                        },
                        "required": ["url"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "github_inspect",
                    "description": (
                        "Inspecte un dépôt GitHub officiel via l'API REST GitHub : métadonnées, "
                        "branche par défaut, licence, 5 derniers commits (date, hash, message, lien), "
                        "3 dernières releases et langages principaux."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo": {
                                "type": "string",
                                "description": "Dépôt au format 'owner/repo' ou URL 'https://github.com/owner/repo'.",
                            },
                        },
                        "required": ["repo"],
                    },
                },
            },
        ]
    )
    tools.extend(CLAIR_TOOL_REGISTRY.to_openai_tools(permissions_from_enabled_tools(enabled_tools)))
    return tools


def _parse_github_repo(raw: str) -> tuple[str, str]:
    text = (raw or "").strip().rstrip("/")
    if not text:
        raise ValueError("Identifiant de dépôt GitHub manquant.")
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        if (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Seules les URLs github.com sont acceptées pour github_inspect.")
        parts = [p for p in parsed.path.split("/") if p]
    else:
        parts = [p for p in text.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Format attendu : 'owner/repo' ou 'https://github.com/owner/repo'.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not _GITHUB_SEGMENT_RE.match(owner) or not _GITHUB_SEGMENT_RE.match(repo):
        raise ValueError("Nom de propriétaire ou de dépôt GitHub invalide.")
    if owner in {".", ".."} or repo in {".", ".."}:
        raise ValueError("Nom de dépôt GitHub non autorisé.")
    return owner, repo


async def _inspect_github_repo(raw_repo: str) -> tuple[dict[str, Any], str]:
    owner, repo = _parse_github_repo(raw_repo)
    base = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cLAIr-Hermes-Agent/1.0",
    }
    async with httpx.AsyncClient(timeout=_GITHUB_TIMEOUT, follow_redirects=False) as client:
        repo_resp = await client.get(base, headers=headers)
        if repo_resp.status_code == 404:
            raise ValueError(f"Dépôt GitHub introuvable : {owner}/{repo}")
        if not repo_resp.is_success:
            raise ValueError(f"API GitHub HTTP {repo_resp.status_code} pour {owner}/{repo}")
        repo_data = repo_resp.json()
        default_branch = str(repo_data.get("default_branch") or "main")

        commits_resp, releases_resp, langs_resp = await client.get(
            f"{base}/commits",
            headers=headers,
            params={"sha": default_branch, "per_page": 5},
        ), await client.get(
            f"{base}/releases",
            headers=headers,
            params={"per_page": 3},
        ), await client.get(
            f"{base}/languages",
            headers=headers,
        )

    commits_raw = commits_resp.json() if commits_resp.is_success else []
    releases_raw = releases_resp.json() if releases_resp.is_success else []
    langs_raw = langs_resp.json() if langs_resp.is_success else {}

    commits = []
    if isinstance(commits_raw, list):
        for item in commits_raw[:5]:
            if not isinstance(item, dict):
                continue
            commit_meta = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            author_meta = commit_meta.get("author") if isinstance(commit_meta.get("author"), dict) else {}
            sha = str(item.get("sha") or "")
            msg = str(commit_meta.get("message") or "").splitlines()[0][:200] if commit_meta.get("message") else ""
            commits.append(
                {
                    "sha": sha,
                    "short_sha": sha[:7],
                    "date": author_meta.get("date"),
                    "author": author_meta.get("name"),
                    "message": msg,
                    "html_url": item.get("html_url"),
                }
            )

    releases = []
    if isinstance(releases_raw, list):
        for rel in releases_raw[:3]:
            if not isinstance(rel, dict):
                continue
            releases.append(
                {
                    "tag_name": rel.get("tag_name"),
                    "name": rel.get("name") or rel.get("tag_name"),
                    "published_at": rel.get("published_at"),
                    "prerelease": bool(rel.get("prerelease", False)),
                    "html_url": rel.get("html_url"),
                }
            )

    languages: list[dict[str, Any]] = []
    if isinstance(langs_raw, dict) and langs_raw:
        total_bytes = sum(v for v in langs_raw.values() if isinstance(v, (int, float)) and v > 0)
        for lang_name, byte_count in list(langs_raw.items())[:8]:
            if isinstance(byte_count, (int, float)) and total_bytes > 0:
                languages.append(
                    {
                        "language": lang_name,
                        "bytes": int(byte_count),
                        "percent": round((byte_count / total_bytes) * 100, 1),
                    }
                )

    license_info = repo_data.get("license") if isinstance(repo_data.get("license"), dict) else {}
    payload = {
        "full_name": repo_data.get("full_name") or f"{owner}/{repo}",
        "html_url": repo_data.get("html_url") or f"https://github.com/{owner}/{repo}",
        "description": repo_data.get("description"),
        "default_branch": default_branch,
        "stargazers_count": repo_data.get("stargazers_count"),
        "forks_count": repo_data.get("forks_count"),
        "open_issues_count": repo_data.get("open_issues_count"),
        "license": license_info.get("spdx_id") or license_info.get("name"),
        "pushed_at": repo_data.get("pushed_at"),
        "updated_at": repo_data.get("updated_at"),
        "latest_commits": commits,
        "latest_releases": releases,
        "languages": languages,
    }
    return payload, f"{payload['full_name']} · {len(commits)} commits, {len(releases)} releases"


def _register_source(sources_acc: list[dict[str, str]], title: str, url: str, snippet: str) -> None:
    clean_url = (url or "").strip()
    if not clean_url:
        return
    if any(item.get("url") == clean_url for item in sources_acc):
        return
    sources_acc.append(
        {
            "title": (title or clean_url)[:140],
            "url": clean_url,
            "snippet": (snippet or "")[:300],
        }
    )


async def execute_hermes_tool(
    settings: Settings,
    name: str,
    raw_arguments: str,
    *,
    sources_acc: list[dict[str, str]],
    registry_ctx: ToolExecutionContext | None = None,
) -> tuple[str, str, bool]:
    """Exécute un outil Hermes local et retourne `(json_result, detail_etape, succes)`."""
    if CLAIR_TOOL_REGISTRY.get(name) is not None:
        ctx = registry_ctx or ToolExecutionContext(
            settings=settings,
            sessions=None,
            user_id=None,
            allowed_permissions=set(),
            sources_acc=sources_acc,
        )
        result = await CLAIR_TOOL_REGISTRY.execute(name, raw_arguments, ctx)
        detail = (
            f"Brouillon créé : {result.title or result.draft_id}"
            if result.success
            else (result.error or "Échec d'exécution d'outil")[:90]
        )
        return result.model_dump_json(), detail, result.success

    try:
        args = json.loads(raw_arguments) if raw_arguments and raw_arguments.strip() else {}
        if not isinstance(args, dict):
            args = {}
    except ValueError:
        return json.dumps({"error": "Arguments JSON invalides."}), "Arguments invalides", False

    try:
        if name == "web_search":
            query = str(args.get("query") or "").strip()
            if not query:
                return json.dumps({"error": "Paramètre 'query' requis."}), "Requête vide", False
            limit_raw = args.get("limit", 5)
            limit = min(max(int(limit_raw) if isinstance(limit_raw, int) else 5, 1), 8)
            results = await providers.search_web(settings, query[:400], limit=limit)
            for src in results:
                _register_source(
                    sources_acc,
                    str(src.get("title") or ""),
                    str(src.get("url") or ""),
                    str(src.get("snippet") or ""),
                )
            return (
                json.dumps({"query": query, "results": results}, ensure_ascii=False),
                f"{len(results)} résultat(s) pour « {query[:60]} »",
                True,
            )

        if name == "fetch_url":
            url = str(args.get("url") or "").strip()
            if not url:
                return json.dumps({"error": "Paramètre 'url' requis."}), "URL vide", False
            filename, _raw, mime_type, extracted_text, extraction = await web.fetch_and_parse_web_url(
                settings, url, allow_private=False
            )
            title = str(extraction.get("title") or filename or url)
            text_out = (extracted_text or "")[:_MAX_FETCH_CHARS]
            _register_source(sources_acc, title, url, text_out[:240])
            return (
                json.dumps(
                    {
                        "url": url,
                        "title": title,
                        "mime_type": mime_type,
                        "truncated": len(extracted_text or "") > _MAX_FETCH_CHARS,
                        "content": text_out,
                    },
                    ensure_ascii=False,
                ),
                f"Page lue ({len(text_out)} car.)",
                True,
            )

        if name == "github_inspect":
            repo = str(args.get("repo") or "").strip()
            payload, detail = await _inspect_github_repo(repo)
            _register_source(
                sources_acc,
                f"GitHub · {payload['full_name']}",
                str(payload["html_url"]),
                str(payload.get("description") or ""),
            )
            return json.dumps(payload, ensure_ascii=False), detail, True

        return json.dumps({"error": f"Outil inconnu : {name}"}), f"Outil inconnu ({name})", False
    except HTTPException as exc:
        msg = str(exc.detail)
        return json.dumps({"error": msg}, ensure_ascii=False), msg[:90], False
    except (providers.ProviderError, httpx.HTTPError, ValueError) as exc:
        msg = str(exc) or "Erreur d'exécution d'outil"
        return json.dumps({"error": msg}, ensure_ascii=False), msg[:90], False
