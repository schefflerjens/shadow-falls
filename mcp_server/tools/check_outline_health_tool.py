import os

from mcp_server.book_codex import (
    parse_codex,
)
from mcp_server.book_outline import compile_full_outline
from mcp_server.mcp_server import server
from mcp_server.prompt_loader import load_prompt
from mcp_server.server_utils import call_ai_model, get_project_model_setting


@server.register_tool(name='check_outline_health', description='Compiles the entire manuscript outline, maps character tracks, and calls the LLM structural editor to produce a Narrative Outline Health Report analyzing pacing, logical timelines, setups/payoffs, and locations.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'current_act': {'type': 'string', 'description': "Optional act/segment (e.g. 'Act 1') to filter chronological Codex timeline states"}}, 'required': ['project_path']})
def check_outline_health_tool(project_path: str, current_act: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        codex_db = parse_codex(expanded_path, current_act=current_act)
        outline_payload = compile_full_outline(expanded_path, codex_db)
        outline_markdown = outline_payload['markdown']
        system_prompt = load_prompt('outline_health_system.txt')
        user_prompt = load_prompt('outline_health_user.txt').replace('{outline_markdown}', outline_markdown)
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        health_report = call_ai_model(system_prompt, user_prompt, model_string=model_string, project_path=expanded_path)
        return {'content': [{'type': 'text', 'text': health_report}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error checking outline health: {str(e)}'}], 'isError': True}
