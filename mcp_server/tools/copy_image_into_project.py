import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='copy_image_into_project', description='Copies an external image file into a project directory under a specific folder node, adding it to the project binder.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target book project directory.'}, 'source_path': {'type': 'string', 'description': 'Absolute path to the source image file on the local filesystem (outside the project).'}, 'target_folder_uuid': {'type': 'string', 'description': 'The UUID of the destination folder inside the project binder.'}, 'image_name': {'type': 'string', 'description': "The name to assign to the image node (e.g. 'cover_art.png')."}}, 'required': ['project_path', 'source_path', 'target_folder_uuid', 'image_name']})
def copy_image_into_project(project_path: str, source_path: str, target_folder_uuid: str, image_name: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        new_uuid = db.copy_image_into_project(source_path, target_folder_uuid, image_name)
        return {'content': [{'type': 'text', 'text': f'Successfully copied image into project under UUID: {new_uuid}'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {e}'}], 'isError': True}
