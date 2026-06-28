import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='copy_image_from_project', description='Copies an image from the project to an external file path or directory on the local filesystem.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target book project directory.'}, 'image_uuid': {'type': 'string', 'description': 'The UUID of the image node to copy out.'}, 'destination_path': {'type': 'string', 'description': "The absolute path where the image should be saved. If it's a directory, the image is saved with its binder name."}}, 'required': ['project_path', 'image_uuid', 'destination_path']})
def copy_image_from_project(project_path: str, image_uuid: str, destination_path: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        db.copy_image_from_project(image_uuid, destination_path)
        return {'content': [{'type': 'text', 'text': f'Successfully copied image from project to {destination_path}'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {e}'}], 'isError': True}
