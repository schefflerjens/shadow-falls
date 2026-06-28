import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='patch_scene', description='Performs a targeted, safe search-and-replace edit on a specific scene draft by UUID. Avoids replacing duplicate blocks.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'uuid': {'type': 'string', 'description': 'The unique UUID of the scene document to edit'}, 'target_text': {'type': 'string', 'description': 'The precise block of existing text inside the draft to replace. Must match exactly and be unique.'}, 'replacement_text': {'type': 'string', 'description': 'The new replacement text to insert in place of the target_text.'}}, 'required': ['project_path', 'uuid', 'target_text', 'replacement_text']})
def patch_scene_tool(project_path: str, uuid: str, target_text: str, replacement_text: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        success = db.patch_scene(uuid, target_text, replacement_text)
        if not success:
            return {'content': [{'type': 'text', 'text': f'Error: Target text not found or not unique in scene {uuid}.'}], 'isError': True}
        return {'content': [{'type': 'text', 'text': f'Successfully patched scene {uuid}.'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error patching scene {uuid}: {str(e)}'}], 'isError': True}
