import concurrent.futures
import json
import os
import sys
import time

from mcp_server.engine.book_engine import get_book_db
from mcp_server.macro_analyzer import (
    analyze_scene,
    get_manuscript_scenes,
    synthesize_macro_report,
)
from mcp_server.mcp_server import server
from mcp_server.server_utils import (
    call_ai_model,
    get_project_genre_benchmarks,
    get_project_model_setting,
    load_env_file,
    write_editor_artifact,
)


@server.register_tool(name='analyze_macro_structure', description='Performs a developmental editing macro-structural audit of a completed Scrivener manuscript (DraftFolder). Generates a SAC database, a high-level Editorial Assessment, and an Open Issues List (timeline & continuity errors).', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'synopsis_path': {'type': 'string', 'description': 'Optional path to an external synopsis file'}, 'chapter_outline_path': {'type': 'string', 'description': 'Optional path to an external chapter outline file'}, 'author_concerns': {'type': 'string', 'description': 'Optional author concerns or goals to guide focus'}}, 'required': ['project_path']})
def analyze_macro_structure_tool(project_path: str, synopsis_path: str=None, chapter_outline_path: str=None, author_concerns: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        benchmarks = get_project_genre_benchmarks(expanded_path)
        style_directives = ''
        try:
            db = get_book_db(expanded_path)
            binder_outline = db.get_outline()
            pd_node = None
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
        synopsis_doc = ''
        if synopsis_path:
            with open(os.path.expanduser(synopsis_path), 'r', encoding='utf-8') as f:
                synopsis_doc = f.read()
        scenes = get_manuscript_scenes(expanded_path)
        if not scenes:
            return {'content': [{'type': 'text', 'text': 'No scenes containing text were found in the Manuscript/Draft folder.'}], 'isError': True}
        load_env_file(expanded_path)
        sac_data = [None] * len(scenes)

        def run_scene_analysis(idx, scene):
            max_retries = 3
            last_err = None
            for attempt in range(max_retries):
                try:
                    res = analyze_scene(scene=scene, scene_index=idx, total_scenes=len(scenes), model_string=model_string, project_path=expanded_path, benchmarks=benchmarks, style_directives=style_directives, call_ai_fn=call_ai_model, author_concerns=author_concerns, synopsis_doc=synopsis_doc)
                    return (idx, res)
                except Exception as e:
                    last_err = e
                    sys.stderr.write(f"Retry {attempt + 1}/{max_retries} for scene '{scene.get('title')}' due to error: {str(e)}\n")
                    sys.stderr.flush()
                    time.sleep(1.0 * (attempt + 1))
            return (idx, {'uuid': scene.get('uuid'), 'scene_title': scene.get('title'), 'chapter': scene.get('chapter'), 'outer_event': f'Error during concurrent analysis: {str(last_err)}', 'writer_intent': {'goal': 'Unknown', 'friction': 'Unknown', 'change': 'Unknown'}, 'thematic_takeaway': 'Unknown', 'subplots': [], 'timeline': {'weekday': None, 'timestamp': None, 'weather': None, 'injuries': None, 'travel': None}})
        max_workers = min(15, len(scenes))
        if max_workers > 0:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_scene_analysis, idx, scene) for idx, scene in enumerate(scenes)]
                for future in concurrent.futures.as_completed(futures):
                    idx, res = future.result()
                    sac_data[idx] = res
        assessment_report, open_issues_list = synthesize_macro_report(sac_data=sac_data, model_string=model_string, project_path=expanded_path, benchmarks=benchmarks, style_directives=style_directives, call_ai_fn=call_ai_model, author_concerns=author_concerns, synopsis_doc=synopsis_doc)
        project_name = os.path.splitext(os.path.basename(expanded_path.rstrip('/')))[0]
        sac_filename = f'{project_name}_SAC_Database.json'
        assessment_filename = f'{project_name}_Macro_Structural_Assessment.md'
        open_issues_filename = f'{project_name}_Open_Issues_List.md'
        sac_content = json.dumps(sac_data, indent=2)
        write_editor_artifact(expanded_path, sac_filename, sac_content)
        write_editor_artifact(expanded_path, assessment_filename, assessment_report)
        write_editor_artifact(expanded_path, open_issues_filename, open_issues_list)
        summary_msg = f"Successfully completed macro-structural analysis for project '{project_name}'!\nAnalyzed {len(scenes)} scenes.\n\nGenerated deliverables in project Notes/Editor:\n1. SAC Database: {sac_filename}\n2. Editorial Assessment: {assessment_filename}\n3. Open Issues List: {open_issues_filename}\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error performing macro-structural analysis: {str(e)}'}], 'isError': True}
