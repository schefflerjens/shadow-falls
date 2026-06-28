import os

from mcp_server.engine.book_engine import get_book_db
from mcp_server.engine.gitbook_engine import GitBookDb
from mcp_server.engine.scrivener_engine import ScrivenerBookDb
from mcp_server.mcp_server import server


@server.register_tool(name='clone_project_structure', description='Clones the outline and structure of an existing project into a new blank project (supports both GitBook and Scrivener).', schema={'type': 'object', 'properties': {'source_project_path': {'type': 'string', 'description': 'Absolute path to the source project package to clone structure from'}, 'target_dir': {'type': 'string', 'description': 'Absolute target directory where the new cloned project should be saved'}, 'new_book_name': {'type': 'string', 'description': 'Display name of the new book (automatically appended with correct extension based on format)'}, 'format': {'type': 'string', 'description': "Project format. Supported: 'gitbook' (for .gitbook), 'scrivener' (for .scriv)", 'default': 'gitbook', 'enum': ['gitbook', 'scrivener']}, 'copy_synopses': {'type': 'boolean', 'description': 'If set to true, replicates synopses/notes in the cloned scenes without the draft text. Defaults to true.', 'default': True}}, 'required': ['source_project_path', 'target_dir', 'new_book_name']})
def clone_project_structure_tool(source_project_path: str, target_dir: str, new_book_name: str, format: str='gitbook', copy_synopses: bool=True) -> dict:
    try:
        expanded_source = os.path.expanduser(source_project_path)
        expanded_target_dir = os.path.expanduser(target_dir)
        source_db = get_book_db(expanded_source)
        if format == 'gitbook':
            new_db = GitBookDb.clone_structure(source_db, expanded_target_dir, new_book_name, copy_synopses)
        else:
            new_db = ScrivenerBookDb.clone_structure(source_db, expanded_target_dir, new_book_name, copy_synopses)
        new_path = new_db.project_path
        return {'content': [{'type': 'text', 'text': f"Successfully cloned structure from '{expanded_source}' to '{new_path}'."}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error cloning project structure: {str(e)}'}], 'isError': True}
