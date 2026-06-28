from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='write_scene', description='Updates the plain text/markdown content, notes, synopsis, and/or title of a scene/document.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'uuid': {'type': 'string', 'description': 'The unique UUID of the scene/document binder item to update'}, 'text': {'type': 'string', 'description': 'The new plain text/markdown story content (optional)'}, 'notes': {'type': 'string', 'description': 'The new plain text/markdown notes content (optional)'}, 'synopsis': {'type': 'string', 'description': 'The new synopsis text content (optional)'}, 'title': {'type': 'string', 'description': 'The new display Title for the binder item (optional)'}}, 'required': ['project_path', 'uuid']})
def write_scene(project_path: str, uuid: str, text: str=None, notes: str=None, synopsis: str=None, title: str=None) -> dict:
    try:
        db = get_book_db(project_path)
        db.write_scene(uuid, text, notes, synopsis)
        if title is not None:
            db.update_binder_item_meta(uuid, title)
        return {'content': [{'type': 'text', 'text': f'Successfully updated scene {uuid}.'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error writing scene {uuid}: {str(e)}'}], 'isError': True}
