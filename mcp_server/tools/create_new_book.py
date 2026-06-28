import os

from mcp_server.engine.gitbook_engine import GitBookDb
from mcp_server.engine.scrivener_engine import ScrivenerBookDb
from mcp_server.mcp_server import server


@server.register_tool(name='create_new_book', description='Creates a brand new GitBook (.gitbook) or Scrivener (.scriv) project from scratch with base folders.', schema={'type': 'object', 'properties': {'target_dir': {'type': 'string', 'description': 'Absolute target parent directory (e.g. ./books or ~/Documents/mybooks)'}, 'book_name': {'type': 'string', 'description': 'Display name of the book project (automatically appended with correct extension based on format)'}, 'format': {'type': 'string', 'description': "Project format. Supported: 'gitbook' (for .gitbook), 'scrivener' (for .scriv)", 'default': 'gitbook', 'enum': ['gitbook', 'scrivener']}}, 'required': ['target_dir', 'book_name']})
def create_new_book(target_dir: str, book_name: str, format: str='gitbook') -> dict:
    try:
        expanded_dir = os.path.expanduser(target_dir)
        if format == 'gitbook':
            db = GitBookDb.create_new(expanded_dir, book_name)
        else:
            db = ScrivenerBookDb.create_new(expanded_dir, book_name)
        project_path = db.project_path
        return {'content': [{'type': 'text', 'text': f'Successfully created new book at {project_path}'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error creating new book: {str(e)}'}], 'isError': True}
