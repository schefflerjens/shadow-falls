import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from mcp_server.engine.book_classes import BinderNode, SceneFiles

# Template Filename Constants
TEMPLATE_PROMPT_DIRECTIVES = "prompt_directives.md"
TEMPLATE_SESSION_MEMORY = "session_memory.md"
TEMPLATE_TASK_CHECKLIST = "task_checklist.md"
TEMPLATE_CHAR_BODY = "char_template.md"
TEMPLATE_CHAR_NOTES = "char_template_notes.md"
TEMPLATE_PLACE_BODY = "place_template.md"
TEMPLATE_PLACE_NOTES = "place_template_notes.md"
TEMPLATE_LORE_BODY = "lore_template.md"
TEMPLATE_LORE_NOTES = "lore_template_notes.md"

# Binder Item Type Constants
TYPE_DRAFT_FOLDER = "DraftFolder"
TYPE_RESEARCH_FOLDER = "ResearchFolder"
TYPE_TRASH_FOLDER = "TrashFolder"
TYPE_FOLDER = "Folder"
TYPE_TEXT = "Text"
TYPE_IMAGE = "Image"

# Core Project Folder Names
FOLDER_MANUSCRIPT = "Manuscript"
FOLDER_CHARACTERS = "Characters"
FOLDER_PLACES = "Places"
FOLDER_NOTES = "Notes"
FOLDER_RESEARCH = "Research"
FOLDER_TRASH = "Trash"

# Agent Workspace Folder/Document Names
FOLDER_AGENT_WORKSPACE = "[Agent Workspace]"
DOC_PROMPT_DIRECTIVES = "Prompt Directives"
DOC_SESSION_MEMORY = "Session Memory"
DOC_TASK_CHECKLIST = "Task Checklist"
FOLDER_CODEX = "Codex"
FOLDER_LORE_FACTIONS = "Lore & Factions"
DOC_CHAR_TEMPLATE = "Character Profile Template"
DOC_PLACE_TEMPLATE = "Location Template"
DOC_LORE_TEMPLATE = "Lore Template"

class BookDb(ABC):
    """
    Abstract interface representing a book database/project engine.
    This interface abstracts away the underlying storage format (e.g. Scrivener .scriv,
    SQLite database, folder of Markdown files, etc.) from the MCP tools.
    """

    # =========================================================================
    # Factory / Creation Methods
    # =========================================================================

    @classmethod
    @abstractmethod
    def exists(cls, project_path: str) -> bool:
        """
        Checks if a project database exists and is valid at the given path.
        
        Args:
            project_path: Absolute path to the project database/directory.
        """
        pass

    @classmethod
    @abstractmethod
    def ensure_safe_to_write(cls, project_path: str) -> None:
        """
        Ensures that the project database at the given path is safe to write to.
        Raises an exception if the project is open/locked by a conflicting application.
        
        Args:
            project_path: Absolute path to the project database/directory.
        """
        pass

    @classmethod
    @abstractmethod
    def create_new(cls, target_dir: str, name: str) -> "BookDb":
        """
        Creates a brand new project/database at the target directory and returns an instance.
        
        Args:
            target_dir: Absolute path to the directory where the project should be created.
            name: The name of the project.
        """
        pass

    @classmethod
    @abstractmethod
    def clone_structure(
        cls, 
        source_db: "BookDb", 
        target_dir: str, 
        new_name: str, 
        copy_synopses: bool = True
    ) -> "BookDb":
        """
        Clones the outline and structure of an existing project into a new blank project.
        
        Args:
            source_db: The source BookDb instance to clone structure from.
            target_dir: Absolute path to the directory where the new project should be created.
            new_name: The name of the new cloned project.
            copy_synopses: If True, copies the binder synopses from the source project.
        """
        pass

    @classmethod
    @abstractmethod
    def create_from_schema(
        cls, 
        target_dir: str, 
        book_name: str, 
        schema: List[Dict[str, Any]]
    ) -> "BookDb":
        """
        Creates a new project populated with a folder/scene outline from a schema.
        
        Args:
            target_dir: Absolute path to the directory where the project should be created.
            book_name: The name of the book project.
            schema: List of dictionary nodes defining folders and scenes.
        """
        pass

    # =========================================================================
    # Binder / Outline Structure
    # =========================================================================

    @abstractmethod
    def get_outline(self) -> List[BinderNode]:
        """
        Retrieves the full hierarchical Binder outline structure of the project.
        """
        pass

    @abstractmethod
    def create_binder_item(
        self, 
        parent_uuid: str, 
        title: str, 
        item_type: str = "Text", 
        position: int = -1
    ) -> str:
        """
        Creates a brand new binder item (scene or folder) under a target parent.
        
        Args:
            parent_uuid: The UUID of the parent folder/group.
            title: The title of the new binder item.
            item_type: Type of item to create (e.g. 'Text', 'Folder').
            position: Insertion index. If -1, appends to the end of the children list.
            
        Returns:
            The unique UUID of the newly created binder item.
        """
        pass

    @abstractmethod
    def update_binder_item_meta(
        self, 
        uuid: str, 
        title: Optional[str] = None
    ) -> bool:
        """
        Updates metadata fields (such as title) of a binder item.
        
        Args:
            uuid: The UUID of the target binder item.
            title: The new title to set. If None, leaves the title unchanged.
            
        Returns:
            True if the update succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def delete_binder_item(
        self, 
        uuid: str, 
        soft_delete: bool = True
    ) -> bool:
        """
        Deletes a specific binder item.
        
        Args:
            uuid: The UUID of the target binder item.
            soft_delete: If True, moves the item to the Trash folder.
                         If False, permanently deletes the item and its files.
                         
        Returns:
            True if the deletion succeeded, False otherwise.
        """
        pass

    # =========================================================================
    # Scene Content Access & Operations
    # =========================================================================

    @abstractmethod
    def read_scene(self, uuid: str) -> SceneFiles:
        """
        Reads the plain text/markdown content, notes, and synopsis of a specific scene.
        
        Args:
            uuid: The UUID of the scene binder item.
            
        Returns:
            A SceneFiles dataclass containing the scene text, notes, and synopsis.
        """
        pass

    @abstractmethod
    def write_scene(
        self, 
        uuid: str, 
        text: Optional[str] = None, 
        notes: Optional[str] = None, 
        synopsis: Optional[str] = None
    ) -> bool:
        """
        Updates the content, notes, and/or synopsis of a specific scene.
        Only fields that are not None will be updated.
        
        Args:
            uuid: The UUID of the scene binder item.
            text: New text/markdown content to write.
            notes: New notes content to write.
            synopsis: New synopsis/beats to write.
            
        Returns:
            True if the update succeeded, False otherwise.
        """
        pass

    # =========================================================================
    # Compilation & Publishing
    # =========================================================================

    @abstractmethod
    def compile_manuscript(self) -> str:
        """
        Stitches the entire active Manuscript (draft folder) into a single unified 
        document in the correct binder order, respecting IncludeInCompile settings.
        
        Returns:
            The compiled manuscript as a single string.
        """
        pass

    # =========================================================================
    # Collaboration Workspace
    # =========================================================================

    @abstractmethod
    def create_agent_workspace(
        self, 
        folder_name: str = "[Agent Workspace]"
    ) -> str:
        """
        Creates a visible, collaborative workspace folder inside the project binder.
        
        Args:
            folder_name: The name of the workspace folder.
            
        Returns:
            The UUID of the newly created workspace folder.
        """
        pass

    # =========================================================================
    # Search
    # =========================================================================

    @abstractmethod
    def search_project(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches case-insensitively across all scene text, notes, and synopses.
        
        Args:
            query: The search query string.
            
        Returns:
            A list of match result dictionaries. Each result contains the item UUID,
            title, type, and snippets of matches in text, notes, or synopsis.
        """
        pass

    # =========================================================================
    # Backup & Snapshotting
    # =========================================================================

    @abstractmethod
    def create_scene_snapshot(
        self, 
        scene_uuid: str, 
        description: str = "Before AI Edit"
    ) -> bool:
        """
        Creates a backup snapshot of the scene's current state.
        
        Args:
            scene_uuid: The UUID of the scene.
            description: Description/name for the snapshot.
            
        Returns:
            True if snapshot creation succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def revert_scene_to_last_snapshot(self, scene_uuid: str) -> Dict[str, Any]:
        """
        Reverts a scene's text, notes, and synopsis to its most recent snapshot.
        
        Args:
            scene_uuid: The UUID of the scene.
            
        Returns:
            A dictionary containing status, success, and the reverted content.
        """
        pass

    # =========================================================================
    # Targeted & Bulk Search-and-Replace
    # =========================================================================

    @abstractmethod
    def patch_scene(
        self, 
        uuid: str, 
        target_text: str, 
        replacement_text: str
    ) -> bool:
        """
        Performs a targeted search-and-replace edit on a specific scene draft.
        
        Args:
            uuid: The UUID of the scene.
            target_text: The unique string to locate.
            replacement_text: The replacement text.
            
        Returns:
            True if the replacement succeeded, False if the target text was not
            found or was not unique inside the scene.
        """
        pass

    @abstractmethod
    def bulk_patch_scenes(
        self,
        target_text: str,
        replacement_text: str,
        scene_uuids: List[str],
        dry_run: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Applies the same exact search-and-replace operation across multiple scenes.
        
        Args:
            target_text: String to locate.
            replacement_text: Replacement string.
            scene_uuids: List of scene UUIDs to process.
            dry_run: If True, only calculates edits without modifying files.
            
        Returns:
            List of result dictionaries indicating changes made or errors per scene.
        """
        pass

    @abstractmethod
    def regex_patch_scenes(
        self,
        pattern: str,
        replacement: str,
        scene_uuids: List[str],
        dry_run: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Applies a regular expression search-and-replace across multiple scenes.
        
        Args:
            pattern: Regular expression pattern to search.
            replacement: Replacement string (supporting capture group backreferences).
            scene_uuids: List of scene UUIDs to process.
            dry_run: If True, only calculates edits without modifying files.
            
        Returns:
            List of result dictionaries indicating changes made or errors per scene.
        """
        pass

    @abstractmethod
    def apply_patchset(
        self,
        patches: List[Dict[str, Any]],
        scene_uuids: Optional[List[str]] = None,
        dry_run: bool = False,
        snapshot_label: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Applies a batch of different replacements (both exact and regex) across 
        multiple scenes in a single atomic/consolidated operation.
        
        Args:
            patches: List of patch dicts containing:
                     - 'type': 'exact' or 'regex'
                     - 'target' / 'pattern': search text
                     - 'replacement': replacement text
            scene_uuids: Optional list of scene UUIDs to process.
            dry_run: If True, only calculates edits without modifying files.
            
        Returns:
            List of result dictionaries indicating changes made or errors per scene.
        """
        pass

    # =========================================================================
    # Image Operations
    # =========================================================================

    @abstractmethod
    def copy_image_into_project(
        self, 
        source_path: str, 
        target_folder_uuid: str, 
        image_name: str
    ) -> str:
        """
        Copies an image from the filesystem into the project, registers it in the
        outline/binder under the specified folder, and returns the new image node's UUID.
        
        Args:
            source_path: Absolute path to the source image file on the local filesystem.
            target_folder_uuid: The UUID of the destination folder inside the project binder.
            image_name: The name/title to assign to the image node.
            
        Returns:
            The unique UUID of the newly created image node.
        """
        pass

    @abstractmethod
    def copy_image_from_project(
        self, 
        image_uuid: str, 
        destination_path: str
    ) -> None:
        """
        Copies the image registered under image_uuid out to an external filesystem destination.
        
        Args:
            image_uuid: The UUID of the image node to copy out.
            destination_path: Absolute path to the target directory or file.
        """
        pass

    @abstractmethod
    def read_image_bytes(
        self, 
        image_uuid: str
    ) -> tuple[bytes, str]:
        """
        Reads the raw binary bytes of the image and detects the appropriate MIME type.
        
        Args:
            image_uuid: The UUID of the image node.
            
        Returns:
            A tuple of (raw_bytes, mime_type).
        """
        pass

    @abstractmethod
    def generate_kdp_cover(
        self,
        image_uuid: str,
        output_name: str
    ) -> str:
        """
        Converts and upscales an image within the project to an Amazon KDP-compliant cover
        (1600x2560 pixels, RGB, JPEG, at 300 DPI) and adds it back to the project.
        
        Args:
            image_uuid: The UUID of the source image node inside the project.
            output_name: The desired name/title for the new KDP cover node (e.g. 'cover_kdp').
            
        Returns:
            The unique UUID of the newly created KDP cover image node.
        """
        pass

def get_book_db(project_path: str) -> BookDb:
    """
    Factory function to retrieve the appropriate BookDb instance based on the project path.
    """
    from mcp_server.engine.in_memory_engine import InMemoryDb
    if project_path in InMemoryDb._registry:
        return InMemoryDb._registry[project_path]

    clean_path = project_path.rstrip("/")
    if clean_path.endswith(".gitbook"):
        from mcp_server.engine.gitbook_engine import GitBookDb
        return GitBookDb(project_path)
    elif clean_path.endswith(".scriv"):
        from mcp_server.engine.scrivener_engine import ScrivenerBookDb
        return ScrivenerBookDb(project_path)
    else:
        raise ValueError(
            f"Unsupported project format at '{project_path}'. "
            "Only '.scriv' and '.gitbook' formats are supported."
        )

def load_template(filename: str) -> str:
    """
    Loads a template file from the mcp_server/templates directory.
    """
    dir_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(dir_path, "templates", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def ensure_safe_to_write(project_path: str) -> None:
    """
    Helper function to check if the project at project_path is safe to write to,
    dispatching dynamically to the correct BookDb backend.
    """
    from mcp_server.engine.in_memory_engine import InMemoryDb
    if project_path in InMemoryDb._registry:
        InMemoryDb.ensure_safe_to_write(project_path)
        return

    clean_path = project_path.rstrip("/")
    if clean_path.endswith(".gitbook"):
        from mcp_server.engine.gitbook_engine import GitBookDb
        GitBookDb.ensure_safe_to_write(project_path)
    elif clean_path.endswith(".scriv"):
        from mcp_server.engine.scrivener_engine import ScrivenerBookDb
        ScrivenerBookDb.ensure_safe_to_write(project_path)
