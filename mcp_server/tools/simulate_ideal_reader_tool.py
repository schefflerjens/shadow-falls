import json
import os
import sys

from mcp_server.book_codex import (
    parse_section_tables,
)
from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.macro_analyzer import (
    get_manuscript_scenes,
    simulate_ideal_reader_analysis,
)
from mcp_server.mcp_server import server
from mcp_server.server_utils import (
    call_ai_model,
    get_project_genre_benchmarks,
    get_project_model_setting,
    load_env_file,
    read_editor_artifact,
    write_editor_artifact,
)


@server.register_tool(name='simulate_ideal_reader', description="Simulates the target audience 'Ideal Reader' persona on the manuscript to produce an Editorial Letter and context-specific inline comments.", schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'persona_profile': {'type': 'string', 'description': 'Override/supplement for the Ideal Reader persona definition (demographic, expectations, comps)', 'default': None}, 'author_concerns': {'type': 'string', 'description': 'Override/supplement for specific questions or concerns the author wants to focus on', 'default': None}}, 'required': ['project_path']})
def simulate_ideal_reader_tool(project_path: str, persona_profile: str=None, author_concerns: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        project_name = os.path.splitext(os.path.basename(expanded_path.rstrip('/')))[0]
        sac_filename = f'{project_name}_SAC_Database.json'
        sac_content = read_editor_artifact(expanded_path, sac_filename)
        if sac_content is None:
            return {'content': [{'type': 'text', 'text': f"Error: SAC Database file '{sac_filename}' not found in project binder under 'Notes/Editor'. Please run the 'analyze_macro_structure' tool first to generate the Scene/Chapter Assessment Chart (SAC) database before simulating the Ideal Reader."}], 'isError': True}
        sac_data = json.loads(sac_content)
        scenes = get_manuscript_scenes(expanded_path)
        if not scenes:
            return {'content': [{'type': 'text', 'text': 'No scenes containing text were found in the Manuscript/Draft folder.'}], 'isError': True}
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        benchmarks = get_project_genre_benchmarks(expanded_path)
        style_directives = ''
        pd_node = None
        binder_outline = db.get_outline()
        try:
            for node in binder_outline:

                def find_node(n, title):
                    if not n:
                        return None
                    if (n.get('title') or '').lower() == title:
                        return n
                    for child in n.get('children') or []:
                        res = find_node(child, title)
                        if res:
                            return res
                    return None
                pd_node = find_node(node, 'prompt directives')
                if pd_node:
                    break
            if pd_node:
                pd_scene = db.read_scene(pd_node['uuid'])
                style_directives = pd_scene.get('text', '')
        except Exception:
            pass
        agent_workspace = None
        for node in binder_outline:
            if '[agent workspace]' in node.get('title', '').lower():
                agent_workspace = node
                break

        def find_node_by_title(node, target_title):
            if not node:
                return None
            title = (node.get('title') or '').lower()
            if target_title in title:
                return node
            for child in node.get('children') or []:
                res = find_node_by_title(child, target_title)
                if res:
                    return res
            return None

        def get_binder_doc_content(target_title):
            doc_node = None
            if agent_workspace:
                doc_node = find_node_by_title(agent_workspace, target_title)
            if not doc_node:
                for root in binder_outline:
                    doc_node = find_node_by_title(root, target_title)
                    if doc_node:
                        break
            if doc_node:
                try:
                    files = db.read_scene(doc_node['uuid'])
                    text = files.get('text', '').strip()
                    notes = files.get('notes', '').strip()
                    parts = []
                    if text:
                        parts.append(text)
                    if notes:
                        parts.append(f'Notes:\n{notes}')
                    return '\n\n'.join(parts).strip()
                except Exception:
                    pass
            return ''
        discovered_persona = get_binder_doc_content('ideal reader')
        if not discovered_persona:
            discovered_persona = get_binder_doc_content('persona profile')
        if not discovered_persona and pd_node:
            try:
                pd_files = db.read_scene(pd_node['uuid'])
                pd_notes = pd_files.get('notes', '')
                sections = parse_section_tables(pd_notes)
                for heading, rows in sections.items():
                    if 'ideal reader' in heading.lower() or 'persona' in heading.lower():
                        discovered_persona = f'### {heading}\n' + '\n'.join([f'- {r[0]}: {r[1]}' for r in rows if len(r) >= 2])
                        break
            except Exception:
                pass
        discovered_concerns = get_binder_doc_content('author concerns')
        if not discovered_concerns:
            discovered_concerns = get_binder_doc_content('author directives')
        if not discovered_concerns and pd_node:
            try:
                pd_files = db.read_scene(pd_node['uuid'])
                pd_notes = pd_files.get('notes', '')
                sections = parse_section_tables(pd_notes)
                for heading, rows in sections.items():
                    if 'author concerns' in heading.lower() or 'directives' in heading.lower() or 'concerns' in heading.lower():
                        discovered_concerns = f'### {heading}\n' + '\n'.join([f'- {r[0]}: {r[1]}' for r in rows if len(r) >= 2])
                        break
            except Exception:
                pass
        discovered_genre_guide = get_binder_doc_content('genre guide')
        if not discovered_genre_guide:
            discovered_genre_guide = get_binder_doc_content('craft brief')
        if not discovered_genre_guide:
            discovered_genre_guide = get_binder_doc_content('writing instructions')
        final_persona = persona_profile or discovered_persona
        final_concerns = author_concerns or discovered_concerns
        if not final_persona:
            return {'content': [{'type': 'text', 'text': "Error: No Ideal Reader persona profile was defined. Please create a binder document titled 'Ideal Reader' in your '[Agent Workspace]' folder or pass the 'persona_profile' parameter to this tool."}], 'isError': True}
        load_env_file(expanded_path)
        editorial_letter, inline_comments_str = simulate_ideal_reader_analysis(sac_data=sac_data, scenes=scenes, persona_profile=final_persona, author_concerns=final_concerns, genre_guide=discovered_genre_guide, model_string=model_string, project_path=expanded_path, benchmarks=benchmarks, style_directives=style_directives, call_ai_fn=call_ai_model)
        inline_comments = []
        if inline_comments_str.strip():
            cleaned_json = inline_comments_str.strip()
            if cleaned_json.startswith('```'):
                lines = cleaned_json.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                cleaned_json = '\n'.join(lines).strip()
            try:
                inline_comments = json.loads(cleaned_json)
            except Exception as e:
                sys.stderr.write(f'Warning: Failed to parse inline comments JSON: {e}\n')
                sys.stderr.flush()
        comments_md = ['# Ideal Reader Inline Comments\n']
        if inline_comments:
            for idx, c in enumerate(inline_comments):
                scene_title = c.get('scene_title') or 'Unknown Scene'
                scene_uuid = c.get('scene_uuid') or 'Unknown UUID'
                anchor = c.get('anchor_text') or ''
                ctype = c.get('type') or 'Developmental Issue'
                comment_text = c.get('comment') or ''
                comments_md.append(f'## Comment {idx + 1}: {ctype}')
                comments_md.append(f'- **Scene:** {scene_title} (UUID: {scene_uuid})')
                if anchor:
                    comments_md.append(f'- **Anchor Text/Quote:** "*{anchor}*"')
                comments_md.append(f'- **Suggestion:** {comment_text}\n')
        else:
            comments_md.append('*No inline comments were successfully generated or parsed.*')
            if inline_comments_str.strip():
                comments_md.append('\n### Raw LLM Output for Inline Comments:\n')
                comments_md.append(inline_comments_str)
        inline_comments_md = '\n'.join(comments_md)
        editorial_letter_filename = f'{project_name}_Ideal_Reader_Editorial_Letter.md'
        inline_json_filename = f'{project_name}_Ideal_Reader_Inline_Comments.json'
        inline_md_filename = f'{project_name}_Ideal_Reader_Inline_Comments.md'
        inline_json_content = json.dumps(inline_comments, indent=2)
        write_editor_artifact(expanded_path, editorial_letter_filename, editorial_letter)
        write_editor_artifact(expanded_path, inline_json_filename, inline_json_content)
        write_editor_artifact(expanded_path, inline_md_filename, inline_comments_md)
        summary_msg = f"Successfully simulated the 'Ideal Reader' persona on project '{project_name}'!\n\nGenerated deliverables in project Notes/Editor:\n1. Editorial Letter: {editorial_letter_filename}\n2. Inline Comments (JSON): {inline_json_filename}\n3. Inline Comments (Markdown): {inline_md_filename}\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error simulating ideal reader: {str(e)}'}], 'isError': True}
