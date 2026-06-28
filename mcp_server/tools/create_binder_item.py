from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='create_binder_item', description='Creates a brand new binder item (scene or folder) under a target parent folder/group.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'parent_uuid': {'type': 'string', 'description': 'The UUID of the parent binder item (e.g. Manuscript folder UUID or a chapter folder UUID)'}, 'title': {'type': 'string', 'description': 'The Title of the new scene or folder'}, 'item_type': {'type': 'string', 'description': "Type of binder item. 'Text' for scenes/documents, 'Folder' for chapters/groups", 'default': 'Text', 'enum': ['Text', 'Folder']}, 'position': {'type': 'integer', 'description': 'Index position under parent children to insert at (starts at 0). Defaults to -1 (append)', 'default': -1}}, 'required': ['project_path', 'parent_uuid', 'title']})
def create_binder_item(project_path: str, parent_uuid: str, title: str, item_type: str='Text', position: int=-1) -> dict:
    try:
        db = get_book_db(project_path)
        new_uuid = db.create_binder_item(parent_uuid, title, item_type, position)
        return {'content': [{'type': 'text', 'text': f"Successfully created {item_type} '{title}' with UUID {new_uuid}."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error creating binder item: {str(e)}'}], 'isError': True}
