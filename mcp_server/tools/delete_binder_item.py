from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='delete_binder_item', description='Deletes a specific binder item (scene or folder) by moving it to the Trash folder or completely deleting it.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'uuid': {'type': 'string', 'description': 'The unique UUID of the scene/document/folder binder item to delete'}, 'hard_delete': {'type': 'boolean', 'description': 'Set to true to completely purge the element from the binder structure instead of moving it to Trash', 'default': False}}, 'required': ['project_path', 'uuid']})
def delete_binder_item(project_path: str, uuid: str, hard_delete: bool=False) -> dict:
    try:
        db = get_book_db(project_path)
        success = db.delete_binder_item(uuid, soft_delete=not hard_delete)
        if not success:
            return {'content': [{'type': 'text', 'text': f'Could not find binder item with UUID {uuid}.'}], 'isError': True}
        action = 'moved to Trash' if not hard_delete else 'hard-deleted'
        return {'content': [{'type': 'text', 'text': f'Successfully {action} binder item {uuid}.'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error deleting binder item: {str(e)}'}], 'isError': True}
