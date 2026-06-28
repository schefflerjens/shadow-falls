import json
import os

from mcp_server.mcp_server import server
from mcp_server.prompt_assembler import compile_writing_prompt


@server.register_tool(name='compile_scene_prompt', description='Compiles and returns the system and user prompts representing the style directives, continuity text, active scene beats, and matching Codex entries.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'scene_uuid': {'type': 'string', 'description': 'The unique UUID of the scene/document binder item'}, 'current_act': {'type': 'string', 'description': "Optional current act or narrative timeline segment (e.g. 'Act 1', 'Act 3') to filter Codex entries"}, 'custom_instructions': {'type': 'string', 'description': 'Optional author constraints or directives'}}, 'required': ['project_path', 'scene_uuid']})
def compile_scene_prompt_tool(project_path: str, scene_uuid: str, current_act: str=None, custom_instructions: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        prompt_payload = compile_writing_prompt(expanded_path, scene_uuid, current_act, custom_instructions)
        return {'content': [{'type': 'text', 'text': json.dumps(prompt_payload, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error compiling prompt: {str(e)}'}], 'isError': True}
