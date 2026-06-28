import os

from mcp_server.engine.gitbook_engine import GitBookDb
from mcp_server.engine.scrivener_engine import ScrivenerBookDb
from mcp_server.mcp_server import server


@server.register_tool(name='create_project_from_schema', description='Creates a new GitBook (.gitbook) or Scrivener (.scriv) project populated with a custom folder/scene outline from a schema.', schema={'type': 'object', 'properties': {'target_dir': {'type': 'string', 'description': 'Absolute target directory where the new project should be saved'}, 'book_name': {'type': 'string', 'description': 'Display name of the new book (automatically appended with correct extension based on format)'}, 'format': {'type': 'string', 'description': "Project format. Supported: 'gitbook' (for .gitbook), 'scrivener' (for .scriv)", 'default': 'gitbook', 'enum': ['gitbook', 'scrivener']}, 'schema': {'type': 'array', 'description': 'A JSON array representing acts, chapters, and scenes with nested children, titles, types, and synopses.', 'items': {'type': 'object', 'properties': {'title': {'type': 'string', 'description': 'The title of the folder or scene'}, 'type': {'type': 'string', 'description': "Type of item: 'Folder' for chapters/sections, 'Text' for scenes", 'enum': ['Folder', 'Text']}, 'synopsis': {'type': 'string', 'description': 'Optional scene synopsis beat instruction'}, 'notes': {'type': 'string', 'description': 'Optional scene reference notes'}, 'children': {'type': 'array', 'description': 'Optional sub-items recursive definition'}}, 'required': ['title', 'type']}}}, 'required': ['target_dir', 'book_name', 'schema']})
def create_project_from_schema_tool(target_dir: str, book_name: str, schema: list, format: str='gitbook') -> dict:
    try:
        expanded_dir = os.path.expanduser(target_dir)
        if format == 'gitbook':
            new_db = GitBookDb.create_from_schema(expanded_dir, book_name, schema)
        else:
            new_db = ScrivenerBookDb.create_from_schema(expanded_dir, book_name, schema)
        new_path = new_db.project_path
        return {'content': [{'type': 'text', 'text': f"Successfully generated new book from schema at '{new_path}'."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error creating project from schema: {str(e)}'}], 'isError': True}
