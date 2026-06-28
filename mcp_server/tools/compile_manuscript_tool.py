import os

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='compile_manuscript', description='Stitches the entire active Manuscript (DraftFolder) into a single, unified Markdown draft document in correct binder order.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}}, 'required': ['project_path']})
def compile_manuscript_tool(project_path: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        compiled_draft = db.compile_manuscript()
        return {'content': [{'type': 'text', 'text': compiled_draft}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error compiling manuscript: {str(e)}'}], 'isError': True}
