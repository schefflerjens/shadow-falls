import json
import os
import re

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server
from mcp_server.readability import compute_readability_metrics
from mcp_server.server_utils import get_project_genre_benchmarks


@server.register_tool(name='get_scene_readability_metrics', description='Calculates and returns raw readability indices and style metrics for a scene draft. Run 100% locally and programmatically (no LLM call).', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the Scrivener (.scriv) project package'}, 'scene_uuid': {'type': 'string', 'description': 'UUID of the target Scene/Text document to analyze'}}, 'required': ['project_path', 'scene_uuid']})
def get_scene_readability_metrics_tool(project_path: str, scene_uuid: str) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        scene_data = db.read_scene(scene_uuid)
        draft_text = scene_data.get('text', '')
        if not draft_text.strip():
            return {'content': [{'type': 'text', 'text': json.dumps({'word_count': 0, 'status': 'empty'})}]}
        metrics = compute_readability_metrics(draft_text)
        cleaned_text = re.sub('<[^>]*>', '', draft_text)
        words = len(re.findall("\\b[a-zA-Z']+\\b", cleaned_text))
        metrics['word_count'] = words
        metrics['status'] = 'success'
        benchmarks = get_project_genre_benchmarks(expanded_path)
        metrics['target_benchmarks'] = benchmarks
        return {'content': [{'type': 'text', 'text': json.dumps(metrics, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}
