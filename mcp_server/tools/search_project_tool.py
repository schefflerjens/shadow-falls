import json
import os

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='search_project', description='Searches case-insensitively across all scene text, notes, and synopses inside the project binder.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'query': {'type': 'string', 'description': 'The search query term to look for (e.g. character name, location, keyword)'}}, 'required': ['project_path', 'query']})
def search_project_tool(project_path: str, query: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        results = db.search_project(query)
        return {'content': [{'type': 'text', 'text': json.dumps(results, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error performing search: {str(e)}'}], 'isError': True}
