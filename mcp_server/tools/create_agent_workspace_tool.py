import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='create_agent_workspace', description='Creates a visible, collaborative [Agent Workspace] folder inside a Scrivener binder with prompt sheets and memory logs.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'folder_name': {'type': 'string', 'description': "Optional name of the workspace folder. Defaults to '[Agent Workspace]'.", 'default': '[Agent Workspace]'}}, 'required': ['project_path']})
def create_agent_workspace_tool(project_path: str, folder_name: str='[Agent Workspace]') -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        workspace_uuid = db.create_agent_workspace(folder_name)
        return {'content': [{'type': 'text', 'text': f"Successfully initialized workspace '{folder_name}' with UUID {workspace_uuid}."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error creating agent workspace: {str(e)}'}], 'isError': True}
