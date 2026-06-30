"""void_manifest — Puranic LLM: think in the Void, manifest in an instant.

The pipeline:
  1. INTENT (natural language app description) — the unmanifest
  2. CONCEPTION (LLM produces ArchitecturalGraph JSON) — the Conscious Void
  3. WITNESS (deterministic validation) — the inner observer
  4. REFINEMENT (LLM fixes issues, if any) — until clean
  5. MANIFESTATION (deterministic compilation to code files) — instant, zero hallucination

This is the Puranic model of creation applied to software: the complete conception
exists in the Void before a single file is written. Once the conception is clean,
manifestation is a mechanical rendering — no generation, no uncertainty.

Usage:
  venv/bin/python -m tools.void_manifest.check "I need a todo app with users, lists, and tasks"
  venv/bin/python -m tools.void_manifest.check --json "A marketplace for handmade goods"
  venv/bin/python -m tools.void_manifest.check --output /tmp/myapp "A blog with comments"
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from tools.void_manifest.arch_schema import ArchitecturalGraph, validate
from tools.void_manifest.render_nextjs import render, write_files
from tools.void_manifest.prompts import build_messages, build_refine_messages


def _envelope(success: bool, data: Any, metadata: Dict[str, Any],
              errors: List[Dict[str, str]]) -> Dict[str, Any]:
    return {"success": success, "data": data,
            "metadata": metadata, "errors": errors}


def _call_llm(messages: List[dict], temperature: float = 0.3) -> str:
    """Call an LLM — tries backend first, falls back to direct HTTP."""
    # Try the existing backend setup first
    try:
        import asyncio
        from backend.main import call_llm_once
        result = asyncio.run(call_llm_once(messages, temperature=temperature))
        if result and result.strip():
            return result
    except Exception:
        pass

    # Fallback: direct API call. Priority: DEEPSEEK (fast) → GEMINI (fast) → DEEPSEEK (slow)
    ds_key = os.getenv("DEEPSEEK_API_KEY")
    gm_key = os.getenv("GEMINI_API_KEY")
    model_override = os.getenv("VOID_MANIFEST_MODEL", "")

    # DeepSeek with v4-flash (fast, 1.5s)
    if ds_key and not ds_key.startswith("your_"):
        ds_model = model_override or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        try:
            import urllib.request as _ur
            body = json.dumps({
                "model": ds_model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }).encode()
            req = _ur.Request(
                "https://api.deepseek.com/chat/completions",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"},
            )
            resp = _ur.urlopen(req)
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            pass  # fall through to Gemini

    # Gemini 2.5 Flash (fast, 1.8s)
    if gm_key and not gm_key.startswith("your_"):
        try:
            import urllib.request as _ur
            body = json.dumps({
                "contents": [{"parts": [{"text": _messages_to_text(messages)}]}],
                "generationConfig": {"temperature": temperature},
            }).encode()
            req = _ur.Request(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + gm_key,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            resp = _ur.urlopen(req)
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            # Strip markdown fences from Gemini output
            return _extract_json_raw(text)
        except Exception as e:
            pass

    # DeepSeek with chat model (slower, fallback)
    if ds_key and not ds_key.startswith("your_"):
        try:
            import urllib.request as _ur
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }).encode()
            req = _ur.Request(
                "https://api.deepseek.com/chat/completions",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"},
            )
            resp = _ur.urlopen(req)
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"All LLM providers failed. Last error: {e}")

    raise RuntimeError("No LLM API key found. Set DEEPSEEK_API_KEY or GEMINI_API_KEY.")


def _extract_json(response: str) -> Dict[str, Any]:
    """Extract JSON from an LLM response that may have markdown wrapping."""
    text = response.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline > 0 else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())


def _extract_json_raw(text: str) -> str:
    """Return raw text (not parsed) — used when the caller handles parsing."""
    return text.strip()


def _messages_to_text(messages: List[dict]) -> str:
    """Convert OpenAI-format messages to a single text string for Gemini native API."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"Instructions: {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def conceive(intent: str, max_refine_rounds: int = 3) -> Dict[str, Any]:
    """The Knower + Witness loop: intent → clean ArchitecturalGraph.

    Returns the standard tool envelope. On success, data.graph holds the
    validated ArchitecturalGraph dict.
    """
    # Step 1: Initial conception
    messages = build_messages(intent)
    try:
        raw = _call_llm(messages, temperature=0.3)
        graph_dict = _extract_json(raw)
    except Exception as e:
        return _envelope(False, None,
                         {"stage": "conception_failed", "rounds": 0},
                         [{"code": "llm_call_failed", "message": str(e)[:200]}])

    # Step 2+3: Witness validation + refinement loop
    for round_num in range(max_refine_rounds + 1):
        try:
            graph = ArchitecturalGraph.from_dict(graph_dict)
        except Exception as e:
            return _envelope(False, None,
                             {"stage": "parse_failed", "rounds": round_num},
                             [{"code": "invalid_graph_format", "message": str(e)[:200]}])

        issues = validate(graph)

        if not issues:
            # Clean — the Void is coherent
            return _envelope(True, graph_dict,
                             {"stage": "conceived", "rounds": round_num + 1,
                              "entities": len(graph.entities),
                              "routes": len(graph.routes),
                              "pages": len(graph.pages),
                              "components": len(graph.components)},
                             [])

        if round_num >= max_refine_rounds:
            # Out of rounds — return with issues
            return _envelope(False, graph_dict,
                             {"stage": "refinement_exhausted", "rounds": round_num + 1,
                              "remaining_issues": len(issues)},
                             issues)

        # Refine: ask LLM to fix
        try:
            refine_msgs = build_refine_messages(json.dumps(graph_dict, indent=2), issues)
            raw = _call_llm(refine_msgs, temperature=0.2)
            graph_dict = _extract_json(raw)
        except Exception as e:
            return _envelope(False, graph_dict,
                             {"stage": "refinement_failed", "rounds": round_num + 1},
                             issues + [{"code": "refine_call_failed", "message": str(e)[:200]}])

    return _envelope(False, graph_dict,
                     {"stage": "loop_exhausted"},
                     [{"code": "max_rounds", "message": "Refinement loop exhausted"}])


def manifest(graph_dict: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
    """The Manifest Engine: ArchitecturalGraph → code files on disk.

    Deterministic. No LLM. No hallucination possible.

    Returns envelope with data.files = list of written relative paths.
    """
    try:
        graph = ArchitecturalGraph.from_dict(graph_dict)
    except Exception as e:
        return _envelope(False, None, {},
                         [{"code": "invalid_graph", "message": str(e)[:200]}])

    # Final witness check
    issues = validate(graph)
    if issues:
        return _envelope(False, None,
                         {"validation_issues": len(issues)},
                         issues)

    try:
        files = render(graph, output_dir)
        written = write_files(files, output_dir)
        return _envelope(True,
                         {"files": written, "total_files": len(written),
                          "output_dir": output_dir},
                         {"entities": len(graph.entities),
                          "routes": len(graph.routes),
                          "pages": len(graph.pages),
                          "components": len(graph.components)},
                         [])
    except Exception as e:
        return _envelope(False, None, {},
                         [{"code": "render_failed", "message": str(e)[:200]}])


def run(intent: str, output_dir: Optional[str] = None,
        max_refine_rounds: int = 3) -> Dict[str, Any]:
    """Full pipeline: intent → conception → manifestation.

    Args:
        intent: Natural language description of the desired application.
        output_dir: Directory to write code files. If None, only conceives
                    (returns the graph without writing files).
        max_refine_rounds: Max LLM refinement rounds for fixing validation issues.

    Returns:
        Standard tool envelope. On success with output_dir, data includes
        'graph' and 'files'. Without output_dir, data is just 'graph'.
    """
    # ── Phase 1+2: Conception (Knower + Witness) ─────────────────────
    conception = conceive(intent, max_refine_rounds=max_refine_rounds)
    if not conception["success"]:
        return conception

    graph_dict = conception["data"]
    metadata = dict(conception["metadata"])
    errors = []

    # ── Phase 3: Manifestation (deterministic) ───────────────────────
    if output_dir:
        manifest_result = manifest(graph_dict, output_dir)
        if not manifest_result["success"]:
            return manifest_result
        metadata.update(manifest_result["metadata"])
        data = {"graph": graph_dict, "files": manifest_result["data"]["files"],
                "output_dir": output_dir, "total_files": manifest_result["data"]["total_files"]}
    else:
        data = {"graph": graph_dict}

    return _envelope(True, data, metadata, errors)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: List[str]) -> int:
    as_json = "--json" in argv
    output_dir = None
    intent_parts = []

    i = 1
    while i < len(argv):
        if argv[i] == "--output" and i + 1 < len(argv):
            output_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--rounds" and i + 1 < len(argv):
            max_rounds = int(argv[i + 1])
            i += 2
        elif argv[i] == "--json":
            i += 1
        else:
            intent_parts.append(argv[i])
            i += 1

    intent = " ".join(intent_parts).strip()
    if not intent:
        print("Usage: python -m tools.void_manifest.check [--output DIR] [--json] APP_DESCRIPTION")
        print("Example: python -m tools.void_manifest.check 'A todo app with users and tasks'")
        return 1

    max_rounds_val = max_rounds if 'max_rounds' in dir() else 3
    env = run(intent, output_dir=output_dir, max_refine_rounds=max_rounds_val)

    if as_json:
        print(json.dumps(env, indent=2, default=str))
    else:
        if not env["success"]:
            print(f"❌ FAILED at stage: {env['metadata'].get('stage', 'unknown')}")
            for err in env.get("errors", []):
                print(f"   [{err['code']}] {err['message']}")
            return 2

        meta = env["metadata"]
        print(f"✓  CONCEPTION complete ({meta.get('rounds', '?')} rounds)")
        print(f"   Entities:   {meta.get('entities', 0)}")
        print(f"   Routes:     {meta.get('routes', 0)}")
        print(f"   Pages:      {meta.get('pages', 0)}")
        print(f"   Components: {meta.get('components', 0)}")

        if env["data"].get("files"):
            print(f"\n✓  MANIFESTATION complete")
            print(f"   Files written: {env['data']['total_files']}")
            print(f"   Output: {env['data']['output_dir']}")
            for f in env["data"]["files"]:
                print(f"   → {f}")

    return 0 if env["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
