import json
import sys

from mcp_server.prompt_loader import load_prompt


def clean_json_response(raw_response: str) -> str:
    """Strips markdown code blocks wrapping JSON if they are present."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned

def extract_scene_continuity(
    scene: dict,
    model_string: str,
    project_path: str,
    call_ai_fn
) -> dict:
    """Extracts characters, locations, timeline markers, terminology, and style notes from a single scene."""
    system_prompt = load_prompt("copyedit_extract_system.txt")

    user_prompt = (
        load_prompt("copyedit_extract_user.txt")
        .replace("{chapter}", scene.get('chapter', 'Unknown'))
        .replace("{title}", scene.get('title', 'Unknown'))
        .replace("{uuid}", scene.get('uuid', 'Unknown'))
        .replace("{scene_text}", scene.get('text', ''))
    )

    raw_response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    raw_response = raw_response or ""
    cleaned = clean_json_response(raw_response)

    try:
        parsed = json.loads(cleaned)
        # Ensure UUID is captured
        parsed["scene_uuid"] = scene.get("uuid")
        parsed["scene_title"] = scene.get("title")
        return parsed
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse scene continuity JSON for {scene.get('title')}: {e}\n")
        sys.stderr.flush()
        return {
            "scene_uuid": scene.get("uuid"),
            "scene_title": scene.get("title"),
            "characters": [],
            "settings": [],
            "invented_terminology": [],
            "timeline": {
                "event": f"JSON Parse Error: {e}",
                "temporal_markers": "",
                "injuries_noted": ""
            },
            "style_mentions": {
                "numbers_format": "",
                "hyphenation": ""
            },
            "raw_error_response": raw_response
        }

def synthesize_continuity_bible(
    scene_extractions: list[dict],
    model_string: str,
    project_path: str,
    style_guide: str,
    orthography: str,
    call_ai_fn
) -> dict:
    """Synthesizes scene-level extractions into a single Master Continuity Bible / Style Sheet, identifying contradictions."""
    system_prompt = load_prompt("copyedit_synthesize_system.txt")

    user_prompt = (
        load_prompt("copyedit_synthesize_user.txt")
        .replace("{style_guide}", style_guide)
        .replace("{orthography}", orthography)
        .replace("{scene_extractions}", json.dumps(scene_extractions, indent=2))
    )

    raw_response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    raw_response = raw_response or ""
    cleaned = clean_json_response(raw_response)

    try:
        return json.loads(cleaned)
    except Exception as e:
        sys.stderr.write(f"Error: Failed to parse synthesised Continuity Bible JSON: {e}\n")
        sys.stderr.flush()
        # Return fallback structure
        return {
            "characters": [],
            "settings": [],
            "invented_terminology": [],
            "timeline": [],
            "style_preferences": {
                "guide": style_guide,
                "orthography": orthography,
                "numbers_format": "Failed to synthesize automatically.",
                "date_format": "",
                "hyphenation_consistency": ""
            },
            "raw_error_response": raw_response
        }

def audit_scene_copyedit(
    scene: dict,
    continuity_bible: dict,
    style_guide: str,
    orthography: str,
    model_string: str,
    project_path: str,
    call_ai_fn
) -> list[dict]:
    """Audits a single scene against the Continuity Bible, Style Guide, Orthography, and fact-checking rules."""
    system_prompt = load_prompt("copyedit_audit_system.txt")

    user_prompt = (
        load_prompt("copyedit_audit_user.txt")
        .replace("{chapter}", scene.get('chapter', 'Unknown'))
        .replace("{title}", scene.get('title', 'Unknown'))
        .replace("{uuid}", scene.get('uuid', 'Unknown'))
        .replace("{style_guide}", style_guide)
        .replace("{orthography}", orthography)
        .replace("{continuity_bible}", json.dumps(continuity_bible, indent=2))
        .replace("{scene_text}", scene.get('text', ''))
    )

    raw_response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    raw_response = raw_response or ""
    cleaned = clean_json_response(raw_response)

    try:
        suggestions = json.loads(cleaned)
        if not isinstance(suggestions, list):
            suggestions = []
        for s in suggestions:
            s["scene_uuid"] = scene.get("uuid")
            s["scene_title"] = scene.get("title")
        return suggestions
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse copyedit suggestions JSON for {scene.get('title')}: {e}\n")
        sys.stderr.flush()
        return []
