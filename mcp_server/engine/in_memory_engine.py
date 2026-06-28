import os
import uuid as uuid_module
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp_server.engine.book_classes import BinderNode, SceneFiles
from mcp_server.engine.book_engine import (
    DOC_CHAR_TEMPLATE,
    DOC_LORE_TEMPLATE,
    DOC_PLACE_TEMPLATE,
    DOC_PROMPT_DIRECTIVES,
    DOC_SESSION_MEMORY,
    DOC_TASK_CHECKLIST,
    FOLDER_AGENT_WORKSPACE,
    FOLDER_CHARACTERS,
    FOLDER_CODEX,
    FOLDER_LORE_FACTIONS,
    FOLDER_MANUSCRIPT,
    FOLDER_NOTES,
    FOLDER_PLACES,
    FOLDER_RESEARCH,
    FOLDER_TRASH,
    TEMPLATE_CHAR_BODY,
    TEMPLATE_CHAR_NOTES,
    TEMPLATE_LORE_BODY,
    TEMPLATE_LORE_NOTES,
    TEMPLATE_PLACE_BODY,
    TEMPLATE_PLACE_NOTES,
    TEMPLATE_PROMPT_DIRECTIVES,
    TEMPLATE_SESSION_MEMORY,
    TEMPLATE_TASK_CHECKLIST,
    TYPE_DRAFT_FOLDER,
    TYPE_FOLDER,
    TYPE_RESEARCH_FOLDER,
    TYPE_TEXT,
    TYPE_TRASH_FOLDER,
    BookDb,
    load_template,
)


class InMemoryDb(BookDb):
    """
    An in-memory implementation of the BookDb interface, useful for testing
    or local-only mock storage of projects.
    """
    _registry = {}

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.outline: List[BinderNode] = []
        self.scene_files: Dict[str, SceneFiles] = {}
        self.snapshots: Dict[str, List[Any]] = {}
        InMemoryDb._registry[project_path] = self

    @classmethod
    def exists(cls, project_path: str) -> bool:
        return project_path in cls._registry

    @classmethod
    def ensure_safe_to_write(cls, project_path: str) -> None:
        pass

    @classmethod
    def create_new(cls, target_dir: str, name: str) -> "InMemoryDb":
        project_path = os.path.join(target_dir, f"{name}.scriv")
        db = cls(project_path)
        default_folders = [
            FOLDER_MANUSCRIPT, FOLDER_CHARACTERS, FOLDER_PLACES,
            FOLDER_NOTES, FOLDER_RESEARCH, FOLDER_TRASH
        ]
        for title in default_folders:
            if title == FOLDER_MANUSCRIPT:
                t = TYPE_DRAFT_FOLDER
            elif title == FOLDER_RESEARCH:
                t = TYPE_RESEARCH_FOLDER
            elif title == FOLDER_TRASH:
                t = TYPE_TRASH_FOLDER
            else:
                t = TYPE_FOLDER

            node = BinderNode(
                uuid=str(uuid_module.uuid4()).upper(),
                type=t,
                title=title,
                created="2026-06-10T13:40:34-04:00",
                modified="2026-06-10T13:40:34-04:00",
                include_in_compile=True,
                children=[]
            )
            db.outline.append(node)
        return db

    @classmethod
    def clone_structure(
        cls, 
        source_db: BookDb, 
        target_dir: str, 
        new_name: str, 
        copy_synopses: bool = True
    ) -> "InMemoryDb":
        project_path = os.path.join(target_dir, f"{new_name}.scriv")
        db = cls(project_path)
        
        def clone_nodes(nodes):
            cloned = []
            for node in nodes:
                orig_notes = ""
                orig_synopsis = ""
                try:
                    orig_scene = source_db.read_scene(node.uuid)
                    orig_notes = orig_scene.notes
                    orig_synopsis = orig_scene.synopsis
                except Exception:
                    pass

                new_node = BinderNode(
                    uuid=node.uuid,
                    type=node.type,
                    title=node.title,
                    created=node.created,
                    modified=node.modified,
                    include_in_compile=node.include_in_compile,
                    children=clone_nodes(node.children)
                )
                cloned.append(new_node)
                
                if node.type == "Text":
                    db.scene_files[node.uuid] = SceneFiles(
                        text="",
                        notes=orig_notes,
                        synopsis=orig_synopsis if copy_synopses else ""
                    )
            return cloned

        db.outline = clone_nodes(source_db.get_outline())
        return db

    @classmethod
    def create_from_schema(
        cls, 
        target_dir: str, 
        book_name: str, 
        schema: list
    ) -> "InMemoryDb":
        db = cls.create_new(target_dir, book_name)
        ms_node = next(n for n in db.outline if n.title == "Manuscript")
        
        def build_children(parent_node, schema_children):
            for child_spec in schema_children:
                child_uuid = str(uuid_module.uuid4()).upper()
                child_node = BinderNode(
                    uuid=child_uuid,
                    type=child_spec.get("type", "Text"),
                    title=child_spec.get("title", "Untitled"),
                    created="2026-06-10T13:40:34-04:00",
                    modified="2026-06-10T13:40:34-04:00",
                    include_in_compile=child_spec.get("include_in_compile", True),
                    children=[]
                )
                parent_node.children.append(child_node)
                if child_node.type == "Text":
                    db.scene_files[child_uuid] = SceneFiles(
                        text=child_spec.get("text", ""),
                        notes=child_spec.get("notes", ""),
                        synopsis=child_spec.get("synopsis", "")
                    )
                if "children" in child_spec:
                    build_children(child_node, child_spec["children"])

        build_children(ms_node, schema)
        return db

    def get_outline(self) -> List[BinderNode]:
        return self.outline

    def create_binder_item(
        self, 
        parent_uuid: str, 
        title: str, 
        item_type: str = "Text", 
        position: int = -1
    ) -> str:
        def find_parent(nodes):
            for node in nodes:
                if node.uuid == parent_uuid:
                    return node
                found = find_parent(node.children)
                if found:
                    return found
            return None

        parent = find_parent(self.outline)
        if not parent:
            raise ValueError(f"Parent UUID {parent_uuid} not found")

        child_uuid = str(uuid_module.uuid4()).upper()
        child_node = BinderNode(
            uuid=child_uuid,
            type=item_type,
            title=title,
            created="2026-06-10T13:40:34-04:00",
            modified="2026-06-10T13:40:34-04:00",
            include_in_compile=True,
            children=[]
        )
        if position == -1:
            parent.children.append(child_node)
        else:
            parent.children.insert(position, child_node)
        
        self.scene_files[child_uuid] = SceneFiles(text="", notes="", synopsis="")
        return child_uuid

    def update_binder_item_meta(
        self, 
        uuid: str, 
        title: str = None
    ) -> bool:
        def find_and_update(nodes):
            for node in nodes:
                if node.uuid == uuid:
                    if title is not None:
                        node.title = title
                    return True
                if find_and_update(node.children):
                    return True
            return False

        return find_and_update(self.outline)

    def delete_binder_item(
        self, 
        uuid: str, 
        soft_delete: bool = True
    ) -> bool:
        def find_item_and_parent(nodes):
            for i, node in enumerate(nodes):
                if node.uuid == uuid:
                    return node, nodes
                res = find_item_and_parent(node.children)
                if res:
                    return res
            return None

        res = find_item_and_parent(self.outline)
        if not res:
            return False

        node, parent_list = res
        parent_list.remove(node)

        if soft_delete:
            trash_node = next((n for n in self.outline if n.title == "Trash"), None)
            if trash_node:
                trash_node.children.append(node)
            else:
                trash_node = BinderNode(
                    uuid=str(uuid_module.uuid4()).upper(),
                    type="Folder",
                    title="Trash",
                    created="2026-06-10T13:40:34-04:00",
                    modified="2026-06-10T13:40:34-04:00",
                    include_in_compile=False,
                    children=[node]
                )
                self.outline.append(trash_node)
        else:
            if uuid in self.scene_files:
                del self.scene_files[uuid]
            if uuid in self.snapshots:
                del self.snapshots[uuid]

        return True

    def read_scene(self, uuid: str) -> SceneFiles:
        if uuid not in self.scene_files:
            def find_node(nodes):
                for node in nodes:
                    if node.uuid == uuid:
                        return True
                    if find_node(node.children):
                        return True
                return False
            if find_node(self.outline):
                self.scene_files[uuid] = SceneFiles(text="", notes="", synopsis="")
            else:
                raise FileNotFoundError(f"Scene files not found for UUID {uuid}")
        return self.scene_files[uuid]

    def write_scene(
        self, 
        uuid: str, 
        text: str = None, 
        notes: str = None, 
        synopsis: str = None
    ) -> bool:
        if uuid not in self.scene_files:
            self.scene_files[uuid] = SceneFiles(text="", notes="", synopsis="")
        
        current = self.scene_files[uuid]
        if text is not None:
            current.text = text
        if notes is not None:
            current.notes = notes
        if synopsis is not None:
            current.synopsis = synopsis
        return True

    def compile_manuscript(self) -> str:
        ms_node = next((n for n in self.outline if n.type == "DraftFolder"), None)
        if not ms_node:
            return ""

        compiled_parts = []
        def traverse_compile(node: BinderNode, depth: int = 1):
            if not node.include_in_compile:
                return
            
            if node.type == "Folder":
                header_char = "#" * min(depth + 1, 6)
                compiled_parts.append(f"\n{header_char} {node.title}\n")
            elif node.type == "Text":
                sf = self.read_scene(node.uuid)
                text_content = sf.text.strip()
                if text_content:
                    scene_header_char = "#" * min(depth + 2, 6)
                    compiled_parts.append(f"\n{scene_header_char} {node.title}\n")
                    compiled_parts.append(text_content)
                    compiled_parts.append("")

            for child in node.children:
                traverse_compile(child, depth + 1)

        for child in ms_node.children:
            traverse_compile(child, depth=1)

        return "\n".join(compiled_parts).strip()

    def create_agent_workspace(
        self, 
        folder_name: str = FOLDER_AGENT_WORKSPACE
    ) -> str:
        existing = next((n for n in self.outline if n.title == folder_name), None)
        if existing:
            return existing.uuid

        workspace_uuid = str(uuid_module.uuid4()).upper()
        workspace_node = BinderNode(
            uuid=workspace_uuid,
            type=TYPE_FOLDER,
            title=folder_name,
            created="2026-06-10T13:40:34-04:00",
            modified="2026-06-10T13:40:34-04:00",
            include_in_compile=False,
            children=[]
        )
        self.outline.append(workspace_node)

        # 1. Prompt Directives
        prompt_directives_text = load_template(TEMPLATE_PROMPT_DIRECTIVES)
        pd_uuid = self.create_binder_item(workspace_uuid, DOC_PROMPT_DIRECTIVES, TYPE_TEXT)
        self.write_scene(pd_uuid, text=prompt_directives_text, notes="", synopsis="AI steering instructions and style guide.")

        # 2. Session Memory
        session_memory_template = load_template(TEMPLATE_SESSION_MEMORY)
        session_memory_text = session_memory_template.replace("{last_sync}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        sm_uuid = self.create_binder_item(workspace_uuid, DOC_SESSION_MEMORY, TYPE_TEXT)
        self.write_scene(sm_uuid, text=session_memory_text, notes="", synopsis="AI agent's persistent memory and history log.")

        # 3. Task Checklist
        task_checklist_text = load_template(TEMPLATE_TASK_CHECKLIST)
        tc_uuid = self.create_binder_item(workspace_uuid, DOC_TASK_CHECKLIST, TYPE_TEXT)
        self.write_scene(tc_uuid, text=task_checklist_text, notes="", synopsis="Current task list and milestone progress tracking.")

        # 4. Codex Folder
        codex_uuid = self.create_binder_item(workspace_uuid, FOLDER_CODEX, TYPE_FOLDER)

        # 5. Codex sub-folders
        chars_sub_uuid = self.create_binder_item(codex_uuid, FOLDER_CHARACTERS, TYPE_FOLDER)
        places_sub_uuid = self.create_binder_item(codex_uuid, FOLDER_PLACES, TYPE_FOLDER)
        lore_sub_uuid = self.create_binder_item(codex_uuid, FOLDER_LORE_FACTIONS, TYPE_FOLDER)

        # Character Profile Template
        char_template_text = load_template(TEMPLATE_CHAR_BODY)
        char_template_notes = load_template(TEMPLATE_CHAR_NOTES)
        ct_uuid = self.create_binder_item(chars_sub_uuid, DOC_CHAR_TEMPLATE, TYPE_TEXT)
        self.write_scene(ct_uuid, text=char_template_text, notes=char_template_notes, synopsis="Standard blueprint for character files.")

        # Location Template
        place_template_text = load_template(TEMPLATE_PLACE_BODY)
        place_template_notes = load_template(TEMPLATE_PLACE_NOTES)
        lt_uuid = self.create_binder_item(places_sub_uuid, DOC_PLACE_TEMPLATE, TYPE_TEXT)
        self.write_scene(lt_uuid, text=place_template_text, notes=place_template_notes, synopsis="Standard blueprint for setting files.")

        # Lore Template
        lore_template_text = load_template(TEMPLATE_LORE_BODY)
        lore_template_notes = load_template(TEMPLATE_LORE_NOTES)
        lore_template_uuid = self.create_binder_item(lore_sub_uuid, DOC_LORE_TEMPLATE, TYPE_TEXT)
        self.write_scene(lore_template_uuid, text=lore_template_text, notes=lore_template_notes, synopsis="Standard blueprint for lore, magic systems, factions, or items.")

        return workspace_uuid

    def search_project(self, query: str) -> List[Dict[str, Any]]:
        results = []
        query_lower = query.lower()

        def find_title_and_type(nodes, uuid):
            for node in nodes:
                if node.uuid == uuid:
                    return node.title, node.type
                found = find_title_and_type(node.children, uuid)
                if found:
                    return found
            return None

        for uuid, sf in self.scene_files.items():
            meta = find_title_and_type(self.outline, uuid)
            if not meta:
                continue
            title, item_type = meta
            
            text_matches = query_lower in sf.text.lower()
            notes_matches = query_lower in sf.notes.lower()
            synopsis_matches = query_lower in sf.synopsis.lower()

            if text_matches or notes_matches or synopsis_matches:
                snippets = {}
                if text_matches:
                    snippets["text"] = {"snippet": f"...{sf.text}..."}
                if notes_matches:
                    snippets["notes"] = {"snippet": f"...{sf.notes}..."}
                if synopsis_matches:
                    snippets["synopsis"] = {"snippet": f"...{sf.synopsis}..."}
                
                results.append({
                    "uuid": uuid,
                    "title": title,
                    "type": item_type,
                    "matches": snippets
                })
        return results

    def create_scene_snapshot(
        self, 
        scene_uuid: str, 
        description: str = "Before AI Edit"
    ) -> bool:
        if scene_uuid not in self.scene_files:
            return False
        current = self.scene_files[scene_uuid]
        if scene_uuid not in self.snapshots:
            self.snapshots[scene_uuid] = []
        self.snapshots[scene_uuid].append((description, SceneFiles(
            text=current.text,
            notes=current.notes,
            synopsis=current.synopsis
        )))
        return True

    def revert_scene_to_last_snapshot(self, scene_uuid: str) -> Dict[str, Any]:
        if scene_uuid not in self.snapshots or not self.snapshots[scene_uuid]:
            return {"success": False, "status": "No snapshot found"}
        
        desc, last = self.snapshots[scene_uuid].pop()
        self.scene_files[scene_uuid] = SceneFiles(
            text=last.text,
            notes=last.notes,
            synopsis=last.synopsis
        )
        return {
            "status": "success",
            "title": desc,
            "date": "2026-06-10 13:40:34",
            "filename": "dummy.rtf"
        }

    def patch_scene(
        self, 
        uuid: str, 
        target_text: str, 
        replacement_text: str
    ) -> bool:
        if uuid not in self.scene_files:
            return False
        current = self.scene_files[uuid]
        if target_text not in current.text:
            return False
        if current.text.count(target_text) != 1:
            return False
        current.text = current.text.replace(target_text, replacement_text)
        return True

    def bulk_patch_scenes(
        self,
        target_text: str,
        replacement_text: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> Dict[str, Any]:
        if snapshotted_uuids is None:
            snapshotted_uuids = set()

        scene_map = {}
        def build_map(node):
            scene_map[node.uuid] = node.title
            for child in node.children:
                build_map(child)
        for root_node in self.outline:
            build_map(root_node)

        total_scenes = len(scene_uuids)
        scenes_modified = 0
        scenes_skipped = 0
        details = []

        label = snapshot_label or f"Bulk Patch: {target_text[:20]} -> {replacement_text[:20]}"

        for scene_uuid in scene_uuids:
            title = scene_map.get(scene_uuid, "Untitled")
            if scene_uuid not in self.scene_files:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Scene not found"
                })
                continue
            sf = self.scene_files[scene_uuid]
            text = sf.text
            if not text:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "No text content"
                })
                continue

            matches = text.count(target_text)
            if matches == 0:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Target text not found"
                })
                continue

            modified = False
            if not dry_run:
                if scene_uuid not in snapshotted_uuids:
                    self.create_scene_snapshot(scene_uuid, label)
                    snapshotted_uuids.add(scene_uuid)
                
                updated_text = text.replace(target_text, replacement_text)
                self.write_scene(scene_uuid, text=updated_text)
                modified = True
                scenes_modified += 1
            else:
                scenes_modified += 1
                modified = True

            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": matches,
                "modified": modified,
                "status": "Success"
            })

        return {
            "total_scenes": total_scenes,
            "scenes_modified": scenes_modified,
            "scenes_skipped": scenes_skipped,
            "details": details
        }

    def regex_patch_scenes(
        self,
        pattern: str,
        replacement: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> Dict[str, Any]:
        import re
        if snapshotted_uuids is None:
            snapshotted_uuids = set()

        scene_map = {}
        def build_map(node):
            scene_map[node.uuid] = node.title
            for child in node.children:
                build_map(child)
        for root_node in self.outline:
            build_map(root_node)

        total_scenes = len(scene_uuids)
        scenes_modified = 0
        scenes_skipped = 0
        details = []

        label = snapshot_label or f"Regex Patch: {pattern[:20]} -> {replacement[:20]}"

        try:
            regex = re.compile(pattern)
        except Exception as e:
            raise ValueError(f"Invalid regex pattern '{pattern}': {e}")

        for scene_uuid in scene_uuids:
            title = scene_map.get(scene_uuid, "Untitled")
            if scene_uuid not in self.scene_files:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Scene not found"
                })
                continue
            sf = self.scene_files[scene_uuid]
            text = sf.text
            if not text:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "No text content"
                })
                continue

            matches = len(regex.findall(text))
            if matches == 0:
                scenes_skipped += 1
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Pattern not found"
                })
                continue

            modified = False
            if not dry_run:
                if scene_uuid not in snapshotted_uuids:
                    self.create_scene_snapshot(scene_uuid, label)
                    snapshotted_uuids.add(scene_uuid)
                
                updated_text = regex.sub(replacement, text)
                self.write_scene(scene_uuid, text=updated_text)
                modified = True
                scenes_modified += 1
            else:
                scenes_modified += 1
                modified = True

            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": matches,
                "modified": modified,
                "status": "Success"
            })

        return {
            "total_scenes": total_scenes,
            "scenes_modified": scenes_modified,
            "scenes_skipped": scenes_skipped,
            "details": details
        }

    def apply_patchset(
        self,
        patches: List[Dict[str, Any]],
        scene_uuids: Optional[List[str]] = None,
        dry_run: bool = False,
        snapshot_label: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        import time
        label = snapshot_label or f"Batch patchset: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        snapshotted_uuids = set()

        patch_results = []
        for idx, patch_dict in enumerate(patches):
            p_type = patch_dict.get("type")
            pattern = patch_dict.get("pattern") or patch_dict.get("target")
            replacement = patch_dict.get("replacement")
            curr_uuids = scene_uuids if scene_uuids is not None else patch_dict.get("scene_uuids", [])

            if p_type == "exact":
                res = self.bulk_patch_scenes(
                    target_text=pattern,
                    replacement_text=replacement,
                    scene_uuids=curr_uuids,
                    dry_run=dry_run,
                    snapshot_label=label,
                    snapshotted_uuids=snapshotted_uuids
                )
            elif p_type == "regex":
                res = self.regex_patch_scenes(
                    pattern=pattern,
                    replacement=replacement,
                    scene_uuids=curr_uuids,
                    dry_run=dry_run,
                    snapshot_label=label,
                    snapshotted_uuids=snapshotted_uuids
                )
            else:
                raise ValueError(f"Unknown patch type '{p_type}' in patch index {idx}")

            patch_results.append({
                "index": idx,
                "type": p_type,
                "pattern": pattern,
                "replacement": replacement,
                "total_scenes": res["total_scenes"],
                "scenes_modified": res["scenes_modified"],
                "scenes_skipped": res["scenes_skipped"]
            })
        return patch_results

    def copy_image_into_project(self, source_path: str, target_folder_uuid: str, image_name: str) -> str:
        raise NotImplementedError("Images are not supported for InMemory projects.")

    def copy_image_from_project(self, image_uuid: str, destination_path: str) -> None:
        raise NotImplementedError("Images are not supported for InMemory projects.")

    def read_image_bytes(self, image_uuid: str) -> tuple[bytes, str]:
        raise NotImplementedError("Images are not supported for InMemory projects.")

    def generate_kdp_cover(self, image_uuid: str, output_name: str) -> str:
        raise NotImplementedError("KDP cover generation is not supported for InMemory projects.")
