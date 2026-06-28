import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='generate_kdp_cover', description='Converts and upscales an image within a project into an Amazon KDP-compliant cover (1600x2560 pixels, RGB, JPEG, at 300 DPI) and adds it back to the project.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target book project directory.'}, 'image_uuid': {'type': 'string', 'description': 'The UUID of the source image node inside the project.'}, 'output_name': {'type': 'string', 'description': "The desired name/title for the new KDP cover image node (e.g. 'cover_kdp')."}}, 'required': ['project_path', 'image_uuid', 'output_name']})
def generate_kdp_cover(project_path: str, image_uuid: str, output_name: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        new_uuid = db.generate_kdp_cover(image_uuid, output_name)
        return {'content': [{'type': 'text', 'text': f'Successfully generated KDP-compliant cover image node under UUID: {new_uuid}'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {e}'}], 'isError': True}
