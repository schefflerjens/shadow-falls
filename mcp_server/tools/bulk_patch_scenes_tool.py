import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='bulk_patch_scenes', description='Applies the same exact string search-and-replace across multiple scenes in a single call, replacing all occurrences per scene.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'target_text': {'type': 'string', 'description': 'The exact target text to search for and replace.'}, 'replacement_text': {'type': 'string', 'description': 'The new replacement text.'}, 'scene_uuids': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Specific scene UUIDs to modify. If omitted or empty, defaults to all compiled manuscript scenes.', 'default': None}, 'dry_run': {'type': 'boolean', 'description': 'If true, checks matches without applying changes or writing snapshots.', 'default': False}}, 'required': ['project_path', 'target_text', 'replacement_text']})
def bulk_patch_scenes_tool(project_path: str, target_text: str, replacement_text: str, scene_uuids: list=None, dry_run: bool=False) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        res = db.bulk_patch_scenes(target_text=target_text, replacement_text=replacement_text, scene_uuids=scene_uuids, dry_run=dry_run)
        dry_prefix = '[DRY RUN] ' if dry_run else ''
        summary_msg = f"{dry_prefix}Successfully completed bulk patch operation!\n\nSummary:\n- Total scenes processed: {res['total_scenes']}\n- Scenes modified: {res['scenes_modified']}\n- Scenes skipped: {res['scenes_skipped']}\n\nDetails per scene:\n"
        for d in res['details']:
            summary_msg += f"- {d['title']} ({d['uuid']}): found {d['matches_found']} match(es), modified={d['modified']} [status={d['status']}]\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error running bulk patch: {str(e)}'}], 'isError': True}
