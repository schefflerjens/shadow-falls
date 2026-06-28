import concurrent.futures
import json
import os
import sys
import time

from mcp_server.book_codex import (
    extract_metadata_from_table,
    parse_section_tables,
)
from mcp_server.copyeditor import (
    extract_scene_continuity,
    synthesize_continuity_bible,
)
from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.macro_analyzer import (
    get_manuscript_scenes,
)
from mcp_server.mcp_server import server
from mcp_server.server_utils import (
    call_ai_model,
    get_project_model_setting,
    load_env_file,
    read_editor_artifact,
    write_editor_artifact,
)


@server.register_tool(name='generate_continuity_bible', description='Analyzes the Scrivener manuscript scene-by-scene to extract facts (characters, descriptions, settings, invented words, timeline events) and synthesizes them into a Master Continuity Bible / Style Sheet.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}}, 'required': ['project_path']})
def generate_continuity_bible_tool(project_path: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        project_name = os.path.splitext(os.path.basename(expanded_path.rstrip('/')))[0]
        sac_filename = f'{project_name}_SAC_Database.json'
        sac_content = read_editor_artifact(expanded_path, sac_filename)
        warning_msg = ''
        if sac_content is None:
            warning_msg = "⚠️ WARNING: You are generating a Continuity Bible before performing a macro-structural audit.\nIt is highly recommended to finalize the story's macro-structure (Phase One & Two) first to avoid wasting computational resources on scenes that may be cut.\n\n"
        scenes = get_manuscript_scenes(expanded_path)
        if not scenes:
            return {'content': [{'type': 'text', 'text': 'No scenes containing text were found in the Manuscript/Draft folder.'}], 'isError': True}
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        style_guide = 'Chicago Manual of Style (CMOS)'
        orthography = 'US'
        try:
            db = get_book_db(expanded_path)
            binder_outline = db.get_outline()
            pd_node = None
            for root_node in binder_outline:
                if '[agent workspace]' in root_node.get('title', '').lower():
                    for child in root_node.get('children', []):
                        if child.get('title', '').lower() == 'prompt directives':
                            pd_node = child
                            break
                    if pd_node:
                        break
            if not pd_node:
                for root_node in binder_outline:
                    if root_node.get('title', '').lower() == 'prompt directives':
                        pd_node = root_node
                        break
            if pd_node:
                pd_files = db.read_scene(pd_node['uuid'])
                pd_notes = pd_files.get('notes', '')
                if pd_notes:
                    sections = parse_section_tables(pd_notes)
                    meta_table = next((rows for heading, rows in sections.items() if 'agent metadata' in heading or 'metadata' in heading), [])
                    if meta_table:
                        metadata = extract_metadata_from_table(meta_table)
                        meta_clean = {k.lower().replace(' ', '_'): v.strip() for k, v in metadata.items()}
                        if 'style_guide' in meta_clean:
                            style_guide = meta_clean['style_guide']
                        elif 'style' in meta_clean:
                            style_guide = meta_clean['style']
                        if 'orthography' in meta_clean:
                            orthography = meta_clean['orthography']
                        elif 'spelling' in meta_clean:
                            orthography = meta_clean['spelling']
        except Exception:
            pass
        load_env_file(expanded_path)
        scene_extractions = [None] * len(scenes)

        def run_scene_extraction(idx, scene):
            max_retries = 3
            last_err = None
            for attempt in range(max_retries):
                try:
                    res = extract_scene_continuity(scene=scene, model_string=model_string, project_path=expanded_path, call_ai_fn=call_ai_model)
                    return (idx, res)
                except Exception as e:
                    last_err = e
                    sys.stderr.write(f"Retry {attempt + 1}/{max_retries} extracting continuity for scene '{scene.get('title')}' due to error: {str(e)}\n")
                    sys.stderr.flush()
                    time.sleep(1.0 * (attempt + 1))
            return (idx, {'scene_uuid': scene.get('uuid'), 'scene_title': scene.get('title'), 'characters': [], 'settings': [], 'invented_terminology': [], 'timeline': {'event': f'Error: {last_err}', 'temporal_markers': '', 'injuries_noted': ''}, 'style_mentions': {'numbers_format': '', 'hyphenation': ''}})
        max_workers = min(15, len(scenes))
        if max_workers > 0:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_scene_extraction, idx, scene) for idx, scene in enumerate(scenes)]
                for future in concurrent.futures.as_completed(futures):
                    idx, res = future.result()
                    scene_extractions[idx] = res
        bible = synthesize_continuity_bible(scene_extractions=scene_extractions, model_string=model_string, project_path=expanded_path, style_guide=style_guide, orthography=orthography, call_ai_fn=call_ai_model)
        bible_json_filename = f'{project_name}_Continuity_Bible.json'
        bible_md_filename = f'{project_name}_Continuity_Bible.md'
        md_lines = []
        md_lines.append(f'# {project_name} - Continuity Bible & Style Sheet\n')
        md_lines.append('## Style Preferences')
        prefs = bible.get('style_preferences', {})
        md_lines.append(f"- **Style Guide:** {prefs.get('guide', style_guide)}")
        md_lines.append(f"- **Orthography:** {prefs.get('orthography', orthography)}")
        md_lines.append(f"- **Numbers Formatting:** {prefs.get('numbers_format', 'N/A')}")
        md_lines.append(f"- **Date Formatting:** {prefs.get('date_format', 'N/A')}")
        md_lines.append(f"- **Hyphenation & Spelling:** {prefs.get('hyphenation_consistency', 'N/A')}\n")
        md_lines.append('## Characters')
        for char in bible.get('characters', []):
            name = char.get('name') or 'Unknown'
            desc = char.get('description') or 'No description.'
            contradictions = char.get('contradictions_found') or []
            md_lines.append(f'### {name}')
            md_lines.append(f'- **Description:** {desc}')
            if contradictions:
                md_lines.append('- **⚠️ Contradictions Found:**')
                for c in contradictions:
                    md_lines.append(f'  - {c}')
            md_lines.append('')
        md_lines.append('## Settings & Locations')
        for setting in bible.get('settings', []):
            name = setting.get('name') or 'Unknown'
            desc = setting.get('description') or 'No description.'
            md_lines.append(f'### {name}')
            md_lines.append(f'- **Details:** {desc}\n')
        md_lines.append('## Invented Terminology')
        for term_item in bible.get('invented_terminology', []):
            term = term_item.get('term') or 'Unknown'
            defn = term_item.get('definition') or 'No definition.'
            md_lines.append(f'- **{term}:** {defn}')
        md_lines.append('')
        md_lines.append('## Master Timeline Log')
        for t in bible.get('timeline', []):
            title = t.get('scene_title') or 'Scene'
            event = t.get('event') or 'No action summarized.'
            markers = t.get('temporal_markers') or 'None'
            injuries = t.get('injuries_noted') or 'None'
            md_lines.append(f'### {title}')
            md_lines.append(f'- **Event:** {event}')
            md_lines.append(f'- **Timeline Markers:** {markers}')
            if injuries and injuries.lower() != 'none':
                md_lines.append(f'- **Injuries/Physical State:** {injuries}')
            md_lines.append('')
        bible_json_content = json.dumps(bible, indent=2)
        bible_md_content = '\n'.join(md_lines)
        write_editor_artifact(expanded_path, bible_json_filename, bible_json_content)
        write_editor_artifact(expanded_path, bible_md_filename, bible_md_content)
        summary_msg = f"{warning_msg}Successfully generated the Continuity Bible & Style Sheet for '{project_name}'!\n\nGenerated deliverables in project Notes/Editor:\n1. Continuity Bible (JSON): {bible_json_filename}\n2. Continuity Bible (Markdown): {bible_md_filename}\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error generating continuity bible: {str(e)}'}], 'isError': True}
