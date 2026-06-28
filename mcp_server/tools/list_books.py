import json
import os

from mcp_server.engine.gitbook_engine import GitBookDb
from mcp_server.engine.scrivener_engine import ScrivenerBookDb
from mcp_server.mcp_server import server
from mcp_server.server_utils import load_env_file

DEFAULT_BOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'books')
if not os.path.exists(DEFAULT_BOOKS_DIR):
    DEFAULT_BOOKS_DIR = os.path.expanduser('~/Documents/mybooks')

@server.register_tool(name='list_books', description='Lists all Scrivener (.scriv) and GitBook (.gitbook) projects in a directory.', schema={'type': 'object', 'properties': {'search_path': {'type': 'string', 'description': f'The path to search for book projects. Defaults to {DEFAULT_BOOKS_DIR}', 'default': DEFAULT_BOOKS_DIR}}})
def list_books(search_path: str=None) -> dict:
    load_env_file()
    roots_env = os.environ.get('PROJECT_ROOTS')
    if search_path is not None and search_path != DEFAULT_BOOKS_DIR or not roots_env:
        if search_path is None:
            search_path = DEFAULT_BOOKS_DIR
        search_paths = [search_path]
    else:
        search_paths = []
        for r in roots_env.split(','):
            r = r.strip()
            if r.startswith(('"', "'")) and r.endswith(r[0]):
                r = r[1:-1]
            r = r.strip()
            if r:
                search_paths.append(r)
        if not search_paths:
            search_paths = [DEFAULT_BOOKS_DIR]
    if len(search_paths) == 1 and (not os.path.exists(os.path.expanduser(search_paths[0]))):
        return {'content': [{'type': 'text', 'text': f'Search directory does not exist: {search_paths[0]}'}]}
    books = []
    seen_paths = set()
    for path in search_paths:
        expanded_path = os.path.expanduser(path)
        if not os.path.exists(expanded_path):
            continue
        try:
            entries = os.listdir(expanded_path)
        except Exception:
            continue
        for entry in entries:
            full_path = os.path.abspath(os.path.join(expanded_path, entry))
            if full_path in seen_paths:
                continue
            if os.path.isdir(full_path):
                if entry.endswith('.scriv'):
                    seen_paths.add(full_path)
                    if ScrivenerBookDb.exists(full_path):
                        books.append({'name': entry[:-6], 'path': full_path, 'format': 'scrivener'})
                    else:
                        books.append({'name': entry, 'path': full_path, 'error': 'Missing .scrivx file inside project package'})
                elif entry.endswith('.gitbook'):
                    seen_paths.add(full_path)
                    if GitBookDb.exists(full_path):
                        books.append({'name': entry[:-8], 'path': full_path, 'format': 'gitbook'})
                    else:
                        books.append({'name': entry, 'path': full_path, 'error': 'Missing binder.json inside project package'})
    return {'content': [{'type': 'text', 'text': json.dumps(books, indent=2)}]}
