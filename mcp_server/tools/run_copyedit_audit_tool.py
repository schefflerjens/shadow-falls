import concurrent.futures
import difflib
import json
import os
import sys
import time
from collections import defaultdict

from mcp_server.copyeditor import (
    audit_scene_copyedit,
)
from mcp_server.engine.book_engine import ensure_safe_to_write
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


@server.register_tool(name='run_copyedit_audit', description='Performs a manuscript-wide mechanical, grammatical, timeline consistency, and fact-checking audit against a Continuity Bible, Style Guide, and Orthography, generating tracked change suggestions (diffs).', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'style_guide': {'type': 'string', 'description': "The style guide to enforce (e.g. 'Chicago Manual of Style (CMOS)', 'AP', 'MLA')", 'default': 'Chicago Manual of Style (CMOS)'}, 'orthography': {'type': 'string', 'description': "Regional orthography/spelling (e.g. 'US' or 'UK')", 'default': 'US'}}, 'required': ['project_path']})
def run_copyedit_audit_tool(project_path: str, style_guide: str='Chicago Manual of Style (CMOS)', orthography: str='US') -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        project_name = os.path.splitext(os.path.basename(expanded_path.rstrip('/')))[0]
        sac_filename = f'{project_name}_SAC_Database.json'
        sac_content = read_editor_artifact(expanded_path, sac_filename)
        warning_msg = ''
        if sac_content is None:
            warning_msg = "⚠️ WARNING: You are running a copyedit audit before performing a macro-structural audit.\nIt is highly recommended to finalize the story's macro-structure (Phase One & Two) first to avoid wasting computational resources on scenes that may be cut.\n\n"
        bible_filename = f'{project_name}_Continuity_Bible.json'
        bible_content = read_editor_artifact(expanded_path, bible_filename)
        if bible_content is None:
            try:
                res = generate_continuity_bible_tool(project_path=project_path)
                if res.get('isError'):
                    return res
                bible_content = read_editor_artifact(expanded_path, bible_filename)
            except Exception as e:
                return {'content': [{'type': 'text', 'text': f'Failed to auto-generate missing Continuity Bible: {e}'}], 'isError': True}
        if bible_content is None:
            return {'content': [{'type': 'text', 'text': 'Failed to read Continuity Bible after auto-generation.'}], 'isError': True}
        continuity_bible = json.loads(bible_content)
        scenes = get_manuscript_scenes(expanded_path)
        if not scenes:
            return {'content': [{'type': 'text', 'text': 'No scenes containing text were found in the Manuscript/Draft folder.'}], 'isError': True}
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        load_env_file(expanded_path)
        all_suggestions = []

        def run_scene_audit(scene):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    res = audit_scene_copyedit(scene=scene, continuity_bible=continuity_bible, style_guide=style_guide, orthography=orthography, model_string=model_string, project_path=expanded_path, call_ai_fn=call_ai_model)
                    return res
                except Exception as e:
                    sys.stderr.write(f"Retry {attempt + 1}/{max_retries} copyediting scene '{scene.get('title')}' due to error: {str(e)}\n")
                    sys.stderr.flush()
                    time.sleep(1.0 * (attempt + 1))
            return []
        max_workers = min(15, len(scenes))
        if max_workers > 0:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_scene_audit, scene) for scene in scenes]
                for future in concurrent.futures.as_completed(futures):
                    all_suggestions.extend(future.result())

        def make_diff(orig, sugg, title):
            orig_lines = orig.splitlines(keepends=True)
            sugg_lines = sugg.splitlines(keepends=True)
            diff = difflib.unified_diff(orig_lines, sugg_lines, fromfile=f'a/{title}', tofile=f'b/{title}')
            return ''.join(diff)
        final_suggestions = []
        for s in all_suggestions:
            orig = s.get('original_text') or ''
            sugg = s.get('suggested_text') or ''
            title = s.get('scene_title') or 'Scene'
            if not orig.strip() and (not sugg.strip()):
                continue
            diff_str = make_diff(orig, sugg, title)
            s['diff'] = diff_str
            final_suggestions.append(s)
        audit_json_filename = f'{project_name}_Copyedit_Audit.json'
        audit_md_filename = f'{project_name}_Copyedit_Audit.md'
        audit_json_content = json.dumps(final_suggestions, indent=2)
        write_editor_artifact(expanded_path, audit_json_filename, audit_json_content)
        md_lines = []
        md_lines.append(f'# Copyedit Audit Report - {project_name}\n')
        md_lines.append(f'- **Style Guide Enforced:** {style_guide}')
        md_lines.append(f'- **Orthography Profile:** {orthography}\n')
        scene_groups = defaultdict(list)
        for s in final_suggestions:
            scene_groups[s.get('scene_title', 'Unknown Scene')].append(s)
        md_lines.append('## Suggestions Summary')
        type_counts = defaultdict(int)
        for s in final_suggestions:
            type_counts[s.get('type', 'Other')] += 1
        for k, v in type_counts.items():
            md_lines.append(f'- **{k}:** {v} issue(s) found')
        md_lines.append('')
        for s_title, group in scene_groups.items():
            md_lines.append(f'## {s_title}')
            for idx, s in enumerate(group):
                md_lines.append(f"### Correction {idx + 1}: {s.get('type', 'Mechanical Error')}")
                md_lines.append(f"**Description:** {s.get('description', 'No explanation provided.')}\n")
                if s.get('original_text'):
                    md_lines.append('**Original Text:**')
                    md_lines.append(f"> {s.get('original_text')}\n")
                if s.get('suggested_text'):
                    md_lines.append('**Suggested Correction:**')
                    md_lines.append(f"> {s.get('suggested_text')}\n")
                if s.get('diff'):
                    md_lines.append('**Tracked Changes (Diff):**')
                    md_lines.append('```diff')
                    md_lines.append(s.get('diff').strip())
                    md_lines.append('```\n')
            md_lines.append('---')
        audit_md_content = '\n'.join(md_lines)
        write_editor_artifact(expanded_path, audit_md_filename, audit_md_content)
        summary_msg = f"{warning_msg}Successfully completed the copyedit audit for '{project_name}'!\n\nAudit Summary:\n" + '\n'.join([f'- {k}: {v} issue(s)' for k, v in type_counts.items()]) + f'\n\nGenerated deliverables in project Notes/Editor:\n1. Copyedit Audit Suggestions (JSON): {audit_json_filename}\n2. Copyedit Audit Report (Markdown): {audit_md_filename}\n'
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error running copyedit audit: {str(e)}'}], 'isError': True}
