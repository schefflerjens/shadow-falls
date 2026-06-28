import os

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server


@server.register_tool(name='apply_patchset', description='Applies a batch of different replacements (both exact and regex) across multiple scenes in one unified operation.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'patches': {'type': 'array', 'description': 'List of patch objects to apply sequentially.', 'items': {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': ['exact', 'regex'], 'description': "The patching type: 'exact' or 'regex'."}, 'pattern': {'type': 'string', 'description': 'Target exact text or regex pattern to match.'}, 'replacement': {'type': 'string', 'description': 'Replacement text.'}, 'scene_uuids': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional scene UUIDs. Defaults to all compiled manuscript scenes if omitted or empty.', 'default': None}}, 'required': ['type', 'pattern', 'replacement']}}, 'snapshot_label': {'type': 'string', 'description': 'Optional snapshot backup label.', 'default': None}, 'dry_run': {'type': 'boolean', 'description': 'If true, simulates all patches without writing to disk.', 'default': False}}, 'required': ['project_path', 'patches']})
def apply_patchset_tool(project_path: str, patches: list, snapshot_label: str=None, dry_run: bool=False) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        patch_results = db.apply_patchset(patches=patches, dry_run=dry_run, snapshot_label=snapshot_label)
        dry_prefix = '[DRY RUN] ' if dry_run else ''
        summary_msg = f'{dry_prefix}Successfully executed patchset batch operation!\n\nBatch Summary:\n'
        for r in patch_results:
            summary_msg += f"- Patch {r['index'] + 1} ({r['type']}): '{r['pattern']}' -> '{r['replacement']}'. Processed={r['total_scenes']}, modified={r['scenes_modified']}, skipped={r['scenes_skipped']}\n"
        return {'content': [{'type': 'text', 'text': summary_msg}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error running patchset batch: {str(e)}'}], 'isError': True}
