import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='regex_patch_scenes', description='Applies a regex-based search-and-replace across multiple scenes in a single call, replacing all occurrences per scene.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'pattern': {'type': 'string', 'description': 'Regular expression pattern to match.'}, 'replacement': {'type': 'string', 'description': 'The replacement string (supports regex backreferences like \\1).'}, 'scene_uuids': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Specific scene UUIDs to modify. If omitted or empty, defaults to all compiled manuscript scenes.', 'default': None}, 'description': {'type': 'string', 'description': 'Description to label the snapshot backup.', 'default': None}, 'dry_run': {'type': 'boolean', 'description': 'If true, checks matches without applying changes or writing snapshots.', 'default': False}}, 'required': ['project_path', 'pattern', 'replacement']})
def regex_patch_scenes_tool(project_path: str, pattern: str, replacement: str, scene_uuids: list=None, description: str=None, dry_run: bool=False) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        res = db.regex_patch_scenes(pattern=pattern, replacement=replacement, scene_uuids=scene_uuids, dry_run=dry_run, snapshot_label=description)
        dry_prefix = '[DRY RUN] ' if dry_run else ''
        summary_msg = f"{dry_prefix}Successfully completed regex patch operation!\n\nSummary:\n- Total scenes processed: {res['total_scenes']}\n- Scenes modified: {res['scenes_modified']}\n- Scenes skipped: {res['scenes_skipped']}\n\nDetails per scene:\n"
        for d in res['details']:
            summary_msg += f"- {d['title']} ({d['uuid']}): found {d['matches_found']} match(es), modified={d['modified']} [status={d['status']}]\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error running regex patch: {str(e)}'}], 'isError': True}
