import json
import os
import re
import shutil
import subprocess
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
    TYPE_IMAGE,
    TYPE_RESEARCH_FOLDER,
    TYPE_TEXT,
    TYPE_TRASH_FOLDER,
    BookDb,
    load_template,
)
from mcp_server.kdp_utils import resize_and_crop_kdp_cover


def sanitize_filename(name: str) -> str:
    if not name:
        return "Untitled"
    # Replace characters that are invalid in Windows/macOS/Linux filesystems
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.strip()
    return name if name else "Untitled"

def load_binder(project_path: str) -> List[BinderNode]:
    binder_path = os.path.join(project_path, "binder.json")
    if not os.path.exists(binder_path):
        return []
    with open(binder_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    def dict_to_node(d: dict, current_path_parts: list[str]) -> BinderNode:
        sanitized = sanitize_filename(d["title"])
        is_folder = d["type"] in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
        if is_folder or d.get("children"):
            next_parts = current_path_parts + [sanitized]
        else:
            next_parts = current_path_parts
        
        node_path = os.path.join(*current_path_parts, sanitized).replace(os.sep, "/")
        
        children = []
        for c in d.get("children", []):
            children.append(dict_to_node(c, next_parts))
            
        return BinderNode(
            uuid=node_path,
            type=d["type"],
            title=d["title"],
            created="",
            modified="",
            include_in_compile=True,
            children=children
        )
        
    return [dict_to_node(n, []) for n in data]

def save_binder(project_path: str, outline: List[BinderNode]):
    binder_path = os.path.join(project_path, "binder.json")
    
    def node_to_dict(node: BinderNode) -> dict:
        return {
            "type": node.type,
            "title": node.title,
            "children": [node_to_dict(c) for c in node.children]
        }
        
    data = [node_to_dict(n) for n in outline]
    with open(binder_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def clean_surrogates(s: str) -> str:
    if not s:
        return ""
    return s.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')

class GitBookDb(BookDb):
    """
    A Git-backed Markdown project engine. Stores book outline in binder.json
    and compile-eligible content in raw markdown files mapped to the binder's
    folder structure, using titles instead of UUIDs.
    Snapshots are versioned using isolated Git commits.
    """

    def __init__(self, project_path: str):
        self.project_path = os.path.abspath(project_path)
        self.outline = load_binder(self.project_path)
        
        # Verify that we are inside a Git repository
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                f"Directory '{project_path}' is not within an active Git repository. "
                "A Git-backed database requires a Git repository."
            )

    @classmethod
    def exists(cls, project_path: str) -> bool:
        binder_path = os.path.join(project_path, "binder.json")
        return os.path.exists(binder_path)

    @classmethod
    def ensure_safe_to_write(cls, project_path: str) -> None:
        pass

    def _get_git_prefix(self) -> str:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-prefix"],
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return res.stdout.strip()
        except Exception:
            return ""

    def _repo_path(self, filename: str) -> str:
        prefix = self._get_git_prefix()
        return os.path.join(prefix, filename).replace(os.sep, "/")

    def _find_node_by_uuid(self, nodes: List[BinderNode], target_uuid: str) -> Optional[BinderNode]:
        for node in nodes:
            if node.uuid == target_uuid:
                return node
            res = self._find_node_by_uuid(node.children, target_uuid)
            if res:
                return res
        return None

    def _find_node_and_path(
        self, 
        nodes: List[BinderNode], 
        target_uuid: str, 
        current_path_parts: List[str]
    ) -> Optional[tuple[BinderNode, str]]:
        for node in nodes:
            sanitized = sanitize_filename(node.title)
            if node.uuid == target_uuid:
                return node, os.path.join(*current_path_parts) if current_path_parts else ""
            
            is_folder = node.type in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
            if is_folder or node.children:
                next_parts = current_path_parts + [sanitized]
            else:
                next_parts = current_path_parts
                
            res = self._find_node_and_path(node.children, target_uuid, next_parts)
            if res:
                return res
        return None

    def _save_and_reload_outline(self):
        save_binder(self.project_path, self.outline)
        self.outline = load_binder(self.project_path)

    @classmethod
    def create_new(cls, target_dir: str, name: str) -> "GitBookDb":
        if not name.endswith(".gitbook"):
            name = name + ".gitbook"
        project_path = os.path.join(target_dir, name)
        os.makedirs(project_path, exist_ok=True)
        
        outline = []
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
                uuid="",
                type=t,
                title=title,
                created="",
                modified="",
                include_in_compile=True,
                children=[]
            )
            outline.append(node)
            
            # Create subfolder on disk immediately
            sanitized = sanitize_filename(title)
            os.makedirs(os.path.join(project_path, sanitized), exist_ok=True)
            
        save_binder(project_path, outline)
        return cls(project_path)

    @classmethod
    def clone_structure(
        cls, 
        source_db: BookDb, 
        target_dir: str, 
        new_name: str, 
        copy_synopses: bool = True
    ) -> "GitBookDb":
        if not new_name.endswith(".gitbook"):
            new_name = new_name + ".gitbook"
        project_path = os.path.join(target_dir, new_name)
        os.makedirs(project_path, exist_ok=True)
        
        db = cls(project_path)
        
        # Clone outline tree structure
        def clone_nodes(nodes):
            cloned = []
            for node in nodes:
                cloned.append(BinderNode(
                    uuid=node.uuid,
                    type=node.type,
                    title=node.title,
                    created="",
                    modified="",
                    include_in_compile=True,
                    children=clone_nodes(node.children)
                ))
            return cloned

        db.outline = clone_nodes(source_db.get_outline())
        db._save_and_reload_outline()
        
        # Create directories and scenes recursively
        def create_folders_and_scenes(nodes):
            for node in nodes:
                res = db._find_node_and_path(db.outline, node.uuid, [])
                if res:
                    node_obj, rel_parent_path = res
                    sanitized_title = sanitize_filename(node_obj.title)
                    is_folder = node_obj.type in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
                    if is_folder:
                        os.makedirs(os.path.join(db.project_path, rel_parent_path, sanitized_title), exist_ok=True)
                    elif node_obj.type == TYPE_TEXT:
                        orig_notes = ""
                        orig_synopsis = ""
                        try:
                            orig_scene = source_db.read_scene(node.uuid)
                            orig_notes = orig_scene.notes
                            orig_synopsis = orig_scene.synopsis
                        except Exception:
                            pass
                        db.write_scene(
                            node.uuid,
                            text="",
                            notes=orig_notes,
                            synopsis=orig_synopsis if copy_synopses else ""
                        )
                create_folders_and_scenes(node.children)
                
        create_folders_and_scenes(db.outline)
        return db

    @classmethod
    def create_from_schema(
        cls, 
        target_dir: str, 
        book_name: str, 
        schema: list
    ) -> "GitBookDb":
        db = cls.create_new(target_dir, book_name)
        ms_node = next(n for n in db.outline if n.title == FOLDER_MANUSCRIPT)
        
        def build_children(parent_node, schema_children):
            for child_spec in schema_children:
                child_node = BinderNode(
                    uuid="",
                    type=child_spec.get("type", TYPE_TEXT),
                    title=child_spec.get("title", "Untitled"),
                    created="",
                    modified="",
                    include_in_compile=True,
                    children=[]
                )
                parent_node.children.append(child_node)
                
                # Save binder tree so paths are resolved
                db._save_and_reload_outline()
                
                # Find the child uuid
                res = db._find_node_and_path(db.outline, child_node.uuid, [])
                if res:
                    _, rel_parent_path = res
                    child_uuid = child_node.uuid
                else:
                    child_uuid = os.path.join(parent_node.uuid, sanitize_filename(child_node.title)).replace(os.sep, "/")
                
                if child_node.type == TYPE_TEXT:
                    db.write_scene(
                        child_uuid,
                        text=child_spec.get("text", ""),
                        notes=child_spec.get("notes", ""),
                        synopsis=child_spec.get("synopsis", "")
                    )
                elif child_node.type == TYPE_FOLDER:
                    # Create folder on disk
                    res = db._find_node_and_path(db.outline, child_uuid, [])
                    if res:
                        _, rel_parent_path = res
                        sanitized = sanitize_filename(child_node.title)
                        os.makedirs(os.path.join(db.project_path, rel_parent_path, sanitized), exist_ok=True)
                
                if "children" in child_spec:
                    reloaded_parent = db._find_node_by_uuid(db.outline, child_uuid)
                    if reloaded_parent:
                        build_children(reloaded_parent, child_spec["children"])

        build_children(ms_node, schema)
        db._save_and_reload_outline()
        return db

    def get_outline(self) -> List[BinderNode]:
        return self.outline

    def create_binder_item(
        self, 
        parent_uuid: str, 
        title: str, 
        item_type: str = TYPE_TEXT, 
        position: int = -1
    ) -> str:
        parent = self._find_node_by_uuid(self.outline, parent_uuid)
        if not parent:
            raise ValueError(f"Parent UUID {parent_uuid} not found")

        child_node = BinderNode(
            uuid="",
            type=item_type,
            title=title,
            created="",
            modified="",
            include_in_compile=True,
            children=[]
        )
        if position == -1:
            parent.children.append(child_node)
        else:
            parent.children.insert(position, child_node)
        
        self._save_and_reload_outline()
        
        # Resolve child_uuid using the parent node inside reloaded outline
        reloaded_parent = self._find_node_by_uuid(self.outline, parent_uuid)
        reloaded_child = next((c for c in reloaded_parent.children if c.title == title), None)
        if not reloaded_child:
            raise RuntimeError("Failed to reload child node after creation")
        child_uuid = reloaded_child.uuid
        
        if item_type == TYPE_TEXT:
            self.write_scene(child_uuid, text="", notes="", synopsis="")
        elif item_type == TYPE_FOLDER:
            # Create folder on disk
            res = self._find_node_and_path(self.outline, child_uuid, [])
            if res:
                _, rel_parent_path = res
                sanitized = sanitize_filename(title)
                os.makedirs(os.path.join(self.project_path, rel_parent_path, sanitized), exist_ok=True)
                
        return child_uuid

    def update_binder_item_meta(
        self, 
        uuid: str, 
        title: str = None
    ) -> bool:
        if title is None:
            return True
            
        res = self._find_node_and_path(self.outline, uuid, [])
        if not res:
            return False
        node, rel_parent_path = res
        old_sanitized = sanitize_filename(node.title)
        new_sanitized = sanitize_filename(title)
        
        # Update title in outline tree
        node.title = title
        self._save_and_reload_outline()
        
        # Rename on disk
        if old_sanitized != new_sanitized:
            parent_dir = os.path.join(self.project_path, rel_parent_path)
            is_folder = node.type in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
            if is_folder:
                old_path = os.path.join(parent_dir, old_sanitized)
                new_path = os.path.join(parent_dir, new_sanitized)
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
            else:
                for suffix in ["", "_notes", "_synopsis"]:
                    ext = ".md"
                    old_file = os.path.join(parent_dir, f"{old_sanitized}{suffix}{ext}")
                    new_file = os.path.join(parent_dir, f"{new_sanitized}{suffix}{ext}")
                    if os.path.exists(old_file):
                        os.rename(old_file, new_file)
                        
        return True

    def delete_binder_item(
        self, 
        uuid: str, 
        soft_delete: bool = True
    ) -> bool:
        res = self._find_node_and_path(self.outline, uuid, [])
        if not res:
            return False
        node, old_rel_parent_path = res
        old_sanitized = sanitize_filename(node.title)
        
        def find_item_and_parent(nodes):
            for i, n in enumerate(nodes):
                if n.uuid == uuid:
                    return n, nodes
                r = find_item_and_parent(n.children)
                if r:
                    return r
            return None

        res_tree = find_item_and_parent(self.outline)
        if not res_tree:
            return False
        node, parent_list = res_tree
        parent_list.remove(node)

        if soft_delete:
            trash_node = next((n for n in self.outline if n.title == FOLDER_TRASH), None)
            if not trash_node:
                trash_node = BinderNode(
                    uuid=FOLDER_TRASH,
                    type=TYPE_FOLDER,
                    title=FOLDER_TRASH,
                    created="",
                    modified="",
                    include_in_compile=False,
                    children=[]
                )
                self.outline.append(trash_node)
            trash_node.children.append(node)
            
            # Save and reload
            self._save_and_reload_outline()
            
            # Move files/folders on disk
            old_dir = os.path.join(self.project_path, old_rel_parent_path)
            new_dir = os.path.join(self.project_path, FOLDER_TRASH)
            os.makedirs(new_dir, exist_ok=True)
            
            is_folder = node.type in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
            if is_folder:
                old_path = os.path.join(old_dir, old_sanitized)
                new_path = os.path.join(new_dir, old_sanitized)
                if os.path.exists(old_path):
                    shutil.move(old_path, new_path)
            else:
                for suffix in ["", "_notes", "_synopsis"]:
                    ext = ".md"
                    old_file = os.path.join(old_dir, f"{old_sanitized}{suffix}{ext}")
                    new_file = os.path.join(new_dir, f"{old_sanitized}{suffix}{ext}")
                    if os.path.exists(old_file):
                        shutil.move(old_file, new_file)
        else:
            # Hard delete
            old_dir = os.path.join(self.project_path, old_rel_parent_path)
            is_folder = node.type in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER)
            if is_folder:
                folder_path = os.path.join(old_dir, old_sanitized)
                if os.path.exists(folder_path):
                    shutil.rmtree(folder_path)
            else:
                for suffix in ["", "_notes", "_synopsis"]:
                    ext = ".md"
                    file_path = os.path.join(old_dir, f"{old_sanitized}{suffix}{ext}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
            
            self._save_and_reload_outline()

        return True

    def read_scene(self, uuid: str) -> SceneFiles:
        res = self._find_node_and_path(self.outline, uuid, [])
        if not res:
            return SceneFiles(text="", notes="", synopsis="")
        node, rel_parent_path = res
        sanitized_title = sanitize_filename(node.title)
        
        parent_dir = os.path.join(self.project_path, rel_parent_path)
        prose_path = os.path.join(parent_dir, f"{sanitized_title}.md")
        notes_path = os.path.join(parent_dir, f"{sanitized_title}_notes.md")
        synopsis_path = os.path.join(parent_dir, f"{sanitized_title}_synopsis.md")
        
        text = ""
        if os.path.exists(prose_path):
            with open(prose_path, "r", encoding="utf-8") as f:
                text = f.read()
                
        notes = ""
        if os.path.exists(notes_path):
            with open(notes_path, "r", encoding="utf-8") as f:
                notes = f.read()
                
        synopsis = ""
        if os.path.exists(synopsis_path):
            with open(synopsis_path, "r", encoding="utf-8") as f:
                synopsis = f.read()
                
        return SceneFiles(text=text, notes=notes, synopsis=synopsis)

    def write_scene(
        self, 
        uuid: str, 
        text: Optional[str] = None, 
        notes: Optional[str] = None, 
        synopsis: Optional[str] = None
    ) -> bool:
        res = self._find_node_and_path(self.outline, uuid, [])
        if not res:
            return False
        node, rel_parent_path = res
        sanitized_title = sanitize_filename(node.title)
        
        parent_dir = os.path.join(self.project_path, rel_parent_path)
        os.makedirs(parent_dir, exist_ok=True)
        
        if text is not None:
            text = clean_surrogates(text)
            prose_path = os.path.join(parent_dir, f"{sanitized_title}.md")
            with open(prose_path, "w", encoding="utf-8") as f:
                f.write(text)
                
        if notes is not None:
            notes = clean_surrogates(notes)
            notes_path = os.path.join(parent_dir, f"{sanitized_title}_notes.md")
            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(notes)
                
        if synopsis is not None:
            synopsis = clean_surrogates(synopsis)
            synopsis_path = os.path.join(parent_dir, f"{sanitized_title}_synopsis.md")
            with open(synopsis_path, "w", encoding="utf-8") as f:
                f.write(synopsis)
                
        return True

    def compile_manuscript(self) -> str:
        ms_node = next((n for n in self.outline if n.type == TYPE_DRAFT_FOLDER), None)
        if not ms_node:
            return ""

        compiled_parts = []
        def traverse_compile(node: BinderNode, depth: int = 1):
            if not node.include_in_compile:
                return
            
            if node.type == TYPE_FOLDER:
                header_char = "#" * min(depth + 1, 6)
                compiled_parts.append(f"\n{header_char} {node.title}\n")
            elif node.type == TYPE_TEXT:
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

        workspace_node = BinderNode(
            uuid="",
            type=TYPE_FOLDER,
            title=folder_name,
            created="",
            modified="",
            include_in_compile=False,
            children=[]
        )
        self.outline.append(workspace_node)
        self._save_and_reload_outline()
        workspace_uuid = FOLDER_AGENT_WORKSPACE

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

        self._save_and_reload_outline()
        return workspace_uuid

    def search_project(self, query: str) -> List[Dict[str, Any]]:
        results = []
        query_lower = query.lower()

        scene_map = {}
        def traverse(node):
            if node.type == TYPE_TEXT:
                scene_map[node.uuid] = (node.title, node.type)
            for child in node.children:
                traverse(child)

        for root_node in self.outline:
            traverse(root_node)

        for uuid, (title, item_type) in scene_map.items():
            try:
                sf = self.read_scene(uuid)
            except Exception:
                continue
            
            text_matches = query_lower in sf.text.lower()
            notes_matches = query_lower in sf.notes.lower()
            synopsis_matches = query_lower in sf.synopsis.lower()

            if text_matches or notes_matches or synopsis_matches:
                snippets = {}
                
                def find_matches_in_field(field_text: str, field_name: str):
                    if not field_text:
                        return
                    if query_lower in field_text.lower():
                        idx = field_text.lower().find(query_lower)
                        start = max(0, idx - 50)
                        end = min(len(field_text), idx + len(query) + 50)
                        snippet = field_text[start:end].replace("\n", " ").strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(field_text):
                            snippet = snippet + "..."
                        snippets[field_name] = {
                            "count": field_text.lower().count(query_lower),
                            "snippet": snippet
                        }

                find_matches_in_field(sf.text, "text")
                find_matches_in_field(sf.notes, "notes")
                find_matches_in_field(sf.synopsis, "synopsis")

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
        self._save_and_reload_outline()
        
        res = self._find_node_and_path(self.outline, scene_uuid, [])
        if not res:
            return False
        node, rel_parent_path = res
        sanitized_title = sanitize_filename(node.title)
        
        prose_rel = os.path.join(rel_parent_path, f"{sanitized_title}.md")
        notes_rel = os.path.join(rel_parent_path, f"{sanitized_title}_notes.md")
        synopsis_rel = os.path.join(rel_parent_path, f"{sanitized_title}_synopsis.md")
        
        to_add = ["binder.json"]
        for rel in [prose_rel, notes_rel, synopsis_rel]:
            if os.path.exists(os.path.join(self.project_path, rel)):
                to_add.append(rel)
                
        try:
            # Stage only these files
            subprocess.run(
                ["git", "add"] + to_add,
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            # Commit only these files
            subprocess.run(
                ["git", "commit", "-m", f"[Snapshot] {scene_uuid}: {description}", "--"] + to_add,
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in e.stdout or "nothing to commit" in e.stderr:
                return True
            raise RuntimeError(f"Failed to create git snapshot: {e.stderr}")
            
        return True

    def revert_scene_to_last_snapshot(self, scene_uuid: str) -> Dict[str, Any]:
        # Find the last commit matching "[Snapshot] {scene_uuid}"
        try:
            res = subprocess.run(
                ["git", "log", f"--grep=\\[Snapshot\\] {scene_uuid}", "-n", "1", "--format=%H"],
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            commit_hash = res.stdout.strip()
        except subprocess.CalledProcessError as e:
            return {"success": False, "status": f"Git log search failed: {e.stderr}"}
            
        if not commit_hash:
            return {"success": False, "status": "No snapshot found"}
            
        res_node = self._find_node_and_path(self.outline, scene_uuid, [])
        if not res_node:
            return {"success": False, "status": "Scene not found in outline"}
        node, rel_parent_path = res_node
        sanitized_title = sanitize_filename(node.title)
        
        prose_rel = os.path.join(rel_parent_path, f"{sanitized_title}.md")
        notes_rel = os.path.join(rel_parent_path, f"{sanitized_title}_notes.md")
        synopsis_rel = os.path.join(rel_parent_path, f"{sanitized_title}_synopsis.md")
        
        prose_repo_path = self._repo_path(prose_rel)
        notes_repo_path = self._repo_path(notes_rel)
        synopsis_repo_path = self._repo_path(synopsis_rel)
        
        def get_file_content(repo_path: str) -> str:
            res_show = subprocess.run(
                ["git", "show", f"{commit_hash}:{repo_path}"],
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res_show.returncode != 0:
                return ""
            return res_show.stdout

        prose_text = get_file_content(prose_repo_path)
        notes_text = get_file_content(notes_repo_path)
        synopsis_text = get_file_content(synopsis_repo_path)
        
        self.write_scene(scene_uuid, text=prose_text, notes=notes_text, synopsis=synopsis_text)
        
        to_add = [prose_rel, notes_rel, synopsis_rel]
        existing_add = [rel for rel in to_add if os.path.exists(os.path.join(self.project_path, rel))]
        
        try:
            subprocess.run(
                ["git", "add"] + existing_add,
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"[Revert] {scene_uuid} to snapshot {commit_hash}", "--"] + existing_add,
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            pass
            
        return {
            "status": "success",
            "title": f"Reverted to snapshot {commit_hash[:8]}",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filename": f"{sanitized_title}.md"
        }

    def patch_scene(
        self, 
        uuid: str, 
        target_text: str, 
        replacement_text: str
    ) -> bool:
        sf = self.read_scene(uuid)
        if not sf.text:
            raise ValueError(f"Scene with UUID {uuid} has no story text content to patch.")
            
        count = sf.text.count(target_text)
        if count == 1:
            updated_text = sf.text.replace(target_text, replacement_text)
            self.write_scene(uuid, text=updated_text)
            return True
        elif count > 1:
            raise ValueError(
                f"Target text was found {count} times in scene {uuid}. "
                "The edit is ambiguous. Please make the target_text more specific."
            )
            
        import re as re_mod
        normalized_target = target_text.replace('…', '...')
        if '...' in normalized_target:
            parts = normalized_target.split('...')
            cleaned_parts = [p for p in parts if p]
            if cleaned_parts:
                pattern_str = r"[\s\S]*?".join(re_mod.escape(p) for p in cleaned_parts)
                matches = list(re_mod.finditer(pattern_str, sf.text))
                if len(matches) == 1:
                    match = matches[0]
                    start, end = match.start(), match.end()
                    updated_text = sf.text[:start] + replacement_text + sf.text[end:]
                    self.write_scene(uuid, text=updated_text)
                    return True
                elif len(matches) > 1:
                    raise ValueError(
                        f"Target text pattern with wildcards was found {len(matches)} times in scene {uuid}. "
                        "The edit is ambiguous. Please make the target_text more specific."
                    )
                    
        raise ValueError(f"Target text was not found in scene {uuid}. Cannot perform patch.")

    def bulk_patch_scenes(
        self,
        target_text: str,
        replacement_text: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        if snapshotted_uuids is None:
            snapshotted_uuids = set()

        scene_map = {}
        def build_map(node):
            scene_map[node.uuid] = node.title
            for child in node.children:
                build_map(child)
        for root_node in self.outline:
            build_map(root_node)

        label = snapshot_label or f"Bulk Patch: {target_text[:20]} -> {replacement_text[:20]}"
        details = []

        for scene_uuid in scene_uuids:
            title = scene_map.get(scene_uuid, "Untitled")
            try:
                sf = self.read_scene(scene_uuid)
                text = sf.text
            except Exception:
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Scene not found"
                })
                continue

            if not text:
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

            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": matches,
                "modified": modified or dry_run,
                "status": "Success"
            })

        return details

    def regex_patch_scenes(
        self,
        pattern: str,
        replacement: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        import re as re_mod
        if snapshotted_uuids is None:
            snapshotted_uuids = set()

        scene_map = {}
        def build_map(node):
            scene_map[node.uuid] = node.title
            for child in node.children:
                build_map(child)
        for root_node in self.outline:
            build_map(root_node)

        label = snapshot_label or f"Regex Patch: {pattern[:20]} -> {replacement[:20]}"
        details = []

        try:
            regex = re_mod.compile(pattern)
        except Exception as e:
            raise ValueError(f"Invalid regex pattern '{pattern}': {e}")

        for scene_uuid in scene_uuids:
            title = scene_map.get(scene_uuid, "Untitled")
            try:
                sf = self.read_scene(scene_uuid)
                text = sf.text
            except Exception:
                details.append({
                    "uuid": scene_uuid,
                    "title": title,
                    "matches_found": 0,
                    "modified": False,
                    "status": "Scene not found"
                })
                continue

            if not text:
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

            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": matches,
                "modified": modified or dry_run,
                "status": "Success"
            })

        return details

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

            scenes_modified = sum(1 for r in res if r["modified"])
            scenes_skipped = len(res) - scenes_modified

            patch_results.append({
                "index": idx,
                "type": p_type,
                "pattern": pattern,
                "replacement": replacement,
                "total_scenes": len(res),
                "scenes_modified": scenes_modified,
                "scenes_skipped": scenes_skipped
            })
        return patch_results

    def copy_image_into_project(self, source_path: str, target_folder_uuid: str, image_name: str) -> str:
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Resolve extension from source_path
        _, ext = os.path.splitext(source_path)
        ext = ext.lower()

        # Sanitize image name
        sanitized_name = sanitize_filename(image_name)
        if not sanitized_name.lower().endswith(ext):
            sanitized_name += ext

        # Find target parent folder
        parent = self._find_node_by_uuid(self.outline, target_folder_uuid)
        if not parent:
            raise ValueError(f"Parent folder UUID '{target_folder_uuid}' not found.")

        # Ensure parent type is a folder
        if parent.type not in (TYPE_DRAFT_FOLDER, TYPE_RESEARCH_FOLDER, TYPE_TRASH_FOLDER, TYPE_FOLDER):
            raise ValueError(f"Parent with UUID '{target_folder_uuid}' is not a folder.")

        # Create new Image binder node
        child_node = BinderNode(
            uuid="",
            type=TYPE_IMAGE,
            title=sanitized_name,
            created="",
            modified="",
            include_in_compile=False,
            children=[]
        )
        parent.children.append(child_node)

        # Save and reload outline
        self._save_and_reload_outline()

        # Find the newly created child node and its parent path
        reloaded_parent = self._find_node_by_uuid(self.outline, target_folder_uuid)
        reloaded_child = next((c for c in reloaded_parent.children if c.title == sanitized_name and c.type == TYPE_IMAGE), None)
        if not reloaded_child:
            raise RuntimeError("Failed to reload child image node after creation.")
        
        child_uuid = reloaded_child.uuid

        # Get parent directory path
        res = self._find_node_and_path(self.outline, child_uuid, [])
        if not res:
            raise RuntimeError("Failed to resolve path for new image node.")
        _, rel_parent_path = res

        target_dir = os.path.join(self.project_path, rel_parent_path)
        os.makedirs(target_dir, exist_ok=True)
        dest_path = os.path.join(target_dir, sanitized_name)

        # Copy the file
        shutil.copy2(source_path, dest_path)

        return child_uuid

    def copy_image_from_project(self, image_uuid: str, destination_path: str) -> None:
        # Find the node and its path
        res = self._find_node_and_path(self.outline, image_uuid, [])
        if not res:
            raise ValueError(f"Image with UUID '{image_uuid}' not found.")
        node, rel_parent_path = res

        if node.type != TYPE_IMAGE:
            raise ValueError(f"Node with UUID '{image_uuid}' is not an Image.")

        # Compute full source path on disk
        source_path = os.path.join(self.project_path, rel_parent_path, node.title)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Image file does not exist on disk: {source_path}")

        # Check if destination_path is a directory
        if os.path.isdir(destination_path):
            dest_file_path = os.path.join(destination_path, node.title)
        else:
            # Check if parent directory of destination_path exists
            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
            dest_file_path = destination_path

        shutil.copy2(source_path, dest_file_path)

    def read_image_bytes(self, image_uuid: str) -> tuple[bytes, str]:
        # Find the node and its path
        res = self._find_node_and_path(self.outline, image_uuid, [])
        if not res:
            raise ValueError(f"Image with UUID '{image_uuid}' not found.")
        node, rel_parent_path = res

        if node.type != TYPE_IMAGE:
            raise ValueError(f"Node with UUID '{image_uuid}' is not an Image.")

        source_path = os.path.join(self.project_path, rel_parent_path, node.title)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Image file does not exist on disk: {source_path}")

        # Read bytes
        with open(source_path, "rb") as f:
            data = f.read()

        # Determine MIME type based on file extension
        ext = os.path.splitext(node.title)[1].lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml"
        }
        mime_type = mime_types.get(ext, "application/octet-stream")

        return data, mime_type

    def generate_kdp_cover(self, image_uuid: str, output_name: str) -> str:
        # Find the source image node and its path
        res = self._find_node_and_path(self.outline, image_uuid, [])
        if not res:
            raise ValueError(f"Source image with UUID '{image_uuid}' not found.")
        source_node, rel_parent_path = res

        if source_node.type != TYPE_IMAGE:
            raise ValueError(f"Source node with UUID '{image_uuid}' is not an Image.")

        source_path = os.path.join(self.project_path, rel_parent_path, source_node.title)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source image file does not exist on disk: {source_path}")

        # Find target parent folder node
        parent_uuid = rel_parent_path.replace(os.sep, "/")
        parent = self._find_node_by_uuid(self.outline, parent_uuid)
        if not parent:
            raise ValueError(f"Parent folder with UUID '{parent_uuid}' not found.")

        # Ensure output name has .jpg extension
        sanitized_name = sanitize_filename(output_name)
        if not sanitized_name.lower().endswith(".jpg") and not sanitized_name.lower().endswith(".jpeg"):
            sanitized_name += ".jpg"

        # Construct destination path
        target_dir = os.path.join(self.project_path, rel_parent_path)
        dest_path = os.path.join(target_dir, sanitized_name)

        # Process and validate the image using the general helper
        resize_and_crop_kdp_cover(source_path, dest_path)


        # Check if the node already exists in parent's children (to avoid duplicates)
        existing_child = next((c for c in parent.children if c.title == sanitized_name and c.type == TYPE_IMAGE), None)
        if existing_child:
            self._save_and_reload_outline()
            return existing_child.uuid

        # Create new Image binder node
        child_node = BinderNode(
            uuid="",
            type=TYPE_IMAGE,
            title=sanitized_name,
            created="",
            modified="",
            include_in_compile=False,
            children=[]
        )
        parent.children.append(child_node)

        # Save and reload outline
        self._save_and_reload_outline()

        # Find the newly created child node and return its UUID
        reloaded_parent = self._find_node_by_uuid(self.outline, parent_uuid)
        reloaded_child = next((c for c in reloaded_parent.children if c.title == sanitized_name and c.type == TYPE_IMAGE), None)
        if not reloaded_child:
            raise RuntimeError("Failed to reload child KDP image node after creation.")

        return reloaded_child.uuid
