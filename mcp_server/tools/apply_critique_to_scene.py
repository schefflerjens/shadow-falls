import json
import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server
from mcp_server.prompt_loader import load_prompt
from mcp_server.server_utils import (
    call_ai_model,
    get_project_genre_benchmarks,
    get_project_model_setting,
)


@server.register_tool(name='apply_critique_to_scene', description='Automatically executes revisions on a Scrivener scene draft to align it with target benchmarks, safely backed up by an XML snapshot.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the Scrivener (.scriv) project package'}, 'scene_uuid': {'type': 'string', 'description': 'UUID of the scene Text document to edit'}, 'critique_text': {'type': 'string', 'description': "The standardized critique report content. If not provided, automatically read from the scene's Notes pane.", 'default': None}}, 'required': ['project_path', 'scene_uuid']})
def apply_critique_to_scene(project_path: str, scene_uuid: str, critique_text: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        scene_data = db.read_scene(scene_uuid)
        draft_text = scene_data.get('text', '')
        if not draft_text.strip():
            return {'content': [{'type': 'text', 'text': 'Scene draft text is empty. Nothing to edit.'}]}
        feedback = critique_text
        if not feedback:
            feedback = scene_data.get('notes', '')
            if not feedback.strip():
                return {'content': [{'type': 'text', 'text': "No critique text provided, and scene Notes are empty. Please run generate_chapter_critique first and paste the report into the scene's notes, or pass it directly."}], 'isError': True}
        snapshot_description = 'Before AI Style Critique Polish'
        try:
            db.create_scene_snapshot(scene_uuid, snapshot_description)
            snapshot_status = f"✅ Native Scrivener XML snapshot backup created successfully: '{snapshot_description}'."
        except Exception as e:
            snapshot_status = f'⚠️ Warning: Failed to create native XML snapshot: {e}. Editing anyway.'
        benchmarks = get_project_genre_benchmarks(expanded_path)
        style_guide = ''
        pd_node = None
        for root_node in db.get_outline():

            def find_node(node, title):
                if node.get('title', '').lower() == title:
                    return node
                for child in node.get('children', []):
                    res = find_node(child, title)
                    if res:
                        return res
                return None
            pd_node = find_node(root_node, 'prompt directives')
            if pd_node:
                break
        if pd_node:
            try:
                style_guide = db.read_scene(pd_node['uuid']).get('text', '')
            except Exception:
                pass
        model_string = get_project_model_setting(expanded_path, task_type='drafting')
        system_prompt = load_prompt('apply_critique_system.txt')
        user_prompt = load_prompt('apply_critique_user.txt').replace('{benchmarks}', json.dumps(benchmarks, indent=2)).replace('{style_guide}', style_guide[:1000]).replace('{feedback}', feedback).replace('{draft_text}', draft_text)
        polished_text = call_ai_model(system_prompt, user_prompt, model_string, expanded_path)
        if not polished_text.strip():
            return {'content': [{'type': 'text', 'text': 'Error: AI returned an empty polished draft.'}], 'isError': True}
        db.write_scene(scene_uuid, text=polished_text, notes=feedback, synopsis=scene_data.get('synopsis', ''))
        return {'content': [{'type': 'text', 'text': f"Successfully executed style critique and polished the chapter draft!\n\n{snapshot_status}\nTarget Genre: {benchmarks['genre']}\nDraft updated inside your Scrivener binder scene '{scene_data.get('title', 'Scene')}'."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error applying critique to scene: {str(e)}'}], 'isError': True}
