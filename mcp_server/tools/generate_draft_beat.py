import json
import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server
from mcp_server.prompt_assembler import compile_writing_prompt
from mcp_server.server_utils import call_ai_model, get_project_model_setting


@server.register_tool(name='generate_draft_beat', description='Compiles context, takes a native snapshot backup, and calls the AI model to generate and append continuing prose for a scene UUID.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'scene_uuid': {'type': 'string', 'description': 'The unique UUID of the scene/document binder item to draft'}, 'current_act': {'type': 'string', 'description': "Optional current act or narrative timeline segment (e.g. 'Act 1', 'Act 3') to filter Codex entries"}, 'custom_instructions': {'type': 'string', 'description': 'Optional author constraints or directives for the generated scene segment'}}, 'required': ['project_path', 'scene_uuid']})
def generate_draft_beat(project_path: str, scene_uuid: str, current_act: str=None, custom_instructions: str=None) -> dict:
    ensure_safe_to_write(project_path)
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        snapshot_success = db.create_scene_snapshot(scene_uuid, 'Before AI Draft Beat')
        snapshot_msg = 'Native backup snapshot created successfully.' if snapshot_success else 'No pre-existing draft text found to snapshot.'
        prompt_payload = compile_writing_prompt(expanded_path, scene_uuid, current_act, custom_instructions)
        model_string = get_project_model_setting(expanded_path, task_type='drafting')
        generated_prose = call_ai_model(prompt_payload['system_prompt'], prompt_payload['user_prompt'], model_string=model_string, project_path=expanded_path)
        scene_files = db.read_scene(scene_uuid)
        current_text = scene_files.get('text', '').strip()
        if current_text:
            updated_text = current_text + '\n\n' + generated_prose.strip()
        else:
            updated_text = generated_prose.strip()
        db.write_scene(scene_uuid, text=updated_text)
        result_payload = {'status': 'success', 'snapshot_backup': snapshot_msg, 'added_prose': generated_prose.strip(), 'full_draft_length': len(updated_text)}
        return {'content': [{'type': 'text', 'text': json.dumps(result_payload, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error generating draft beat: {str(e)}'}], 'isError': True}
