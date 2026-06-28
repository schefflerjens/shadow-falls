import dataclasses
import json

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='read_scene', description='Reads plain text/markdown content, notes, and synopsis of a specific scene/document by UUID.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'uuid': {'type': 'string', 'description': 'The unique UUID of the scene/document binder item'}}, 'required': ['project_path', 'uuid']})
def read_scene(project_path: str, uuid: str) -> dict:
    try:
        db = get_book_db(project_path)
        data = db.read_scene(uuid)
        return {'content': [{'type': 'text', 'text': json.dumps(dataclasses.asdict(data), indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error reading scene {uuid}: {str(e)}'}], 'isError': True}
