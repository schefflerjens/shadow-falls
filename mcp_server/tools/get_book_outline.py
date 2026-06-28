import dataclasses
import json

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='get_book_outline', description='Retrieves the full hierarchical Binder outline structure of a Scrivener project.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}}, 'required': ['project_path']})
def get_book_outline(project_path: str) -> dict:
    try:
        db = get_book_db(project_path)
        outline = db.get_outline()
        outline_dicts = [dataclasses.asdict(node) for node in outline]
        return {'content': [{'type': 'text', 'text': json.dumps(outline_dicts, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error parsing book outline: {str(e)}'}], 'isError': True}
