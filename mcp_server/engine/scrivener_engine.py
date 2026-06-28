import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional


def write_scrivx(tree: ET.ElementTree, path: str):
    """Writes the ElementTree back to standard scrivx format with double-quoted UTF-8 header."""
    ET.indent(tree, space="    ")
    xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8")
    xml_str = xml_bytes.decode("utf-8")
    final_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
    with open(path, "w", encoding="utf-8") as f:
        f.write(final_content)

def find_scrivx_path(project_path: str) -> str:
    """Finds the .scrivx file inside a .scriv package directory."""
    if not os.path.exists(project_path):
        raise FileNotFoundError(f"Project path not found: {project_path}")
    
    project_name = os.path.basename(project_path.rstrip("/"))
    if project_name.endswith(".scriv"):
        project_name = project_name[:-6]
    
    scrivx_path = os.path.join(project_path, f"{project_name}.scrivx")
    if os.path.exists(scrivx_path):
        return scrivx_path
        
    # Fallback: find any .scrivx file in the root of the scriv package
    for f in os.listdir(project_path):
        if f.endswith(".scrivx"):
            return os.path.join(project_path, f)
            
    raise FileNotFoundError(f"Could not find .scrivx file in {project_path}")

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


def element_to_dict(elem: ET.Element) -> BinderNode:
    """Converts a BinderItem XML element into a typesafe BinderNode representation."""
    if elem.tag != "BinderItem":
        return None
        
    item_uuid = elem.attrib.get("UUID")
    item_type = elem.attrib.get("Type")
    created = elem.attrib.get("Created")
    modified = elem.attrib.get("Modified")
    
    title = ""
    title_elem = elem.find("Title")
    if title_elem is not None:
        title = title_elem.text or ""
        
    include_in_compile = True
    meta = elem.find("MetaData")
    if meta is not None:
        inc = meta.find("IncludeInCompile")
        if inc is not None and inc.text == "No":
            include_in_compile = False

    children = []
    children_elem = elem.find("Children")
    if children_elem is not None:
        for child in children_elem.findall("BinderItem"):
            node = element_to_dict(child)
            if node:
                children.append(node)
            
    return BinderNode(
        uuid=item_uuid,
        type=item_type,
        title=title,
        created=created,
        modified=modified,
        include_in_compile=include_in_compile,
        children=children
    )

def parse_binder(scrivx_path: str) -> List[BinderNode]:
    """Parses the XML and returns the full Binder tree outline as typesafe BinderNodes."""
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    binder = root.find("Binder")
    if binder is None:
        return []
        
    outline = []
    for item in binder.findall("BinderItem"):
        node = element_to_dict(item)
        if node:
            outline.append(node)
    return outline

def find_binder_item_element(root: ET.Element, target_uuid: str) -> ET.Element:
    """Recursively searches for a BinderItem by UUID."""
    for item in root.iter("BinderItem"):
        if item.attrib.get("UUID") == target_uuid:
            return item
    return None

def find_parent_element(root: ET.Element, child_uuid: str) -> tuple:
    """Finds the parent element of a BinderItem and the child itself."""
    for item in root.iter("BinderItem"):
        children_elem = item.find("Children")
        if children_elem is not None:
            for child in children_elem.findall("BinderItem"):
                if child.attrib.get("UUID") == child_uuid:
                    return children_elem, child
                    
    # Also check at root level of <Binder>
    binder = root.find("Binder")
    if binder is not None:
        for child in binder.findall("BinderItem"):
            if child.attrib.get("UUID") == child_uuid:
                return binder, child
                
    return None, None

def insert_binder_item(scrivx_path: str, parent_uuid: str, new_item_title: str, new_item_type: str = "Text", position: int = -1) -> str:
    """Inserts a new BinderItem in the XML and saves it. Returns the new UUID."""
    import time
    tz = time.strftime("%z")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + tz

    new_uuid = str(uuid.uuid4()).upper()
    
    # Parse the XML
    ET.register_namespace('', '')
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    # Find parent element
    parent_elem = find_binder_item_element(root, parent_uuid)
    
    # If parent is not found, let's see if we should insert at the root <Binder>
    if parent_elem is None:
        binder = root.find("Binder")
        if binder is None:
            raise ValueError("Invalid Scrivener file: no <Binder> root found.")
        parent_container = binder
    else:
        # We need to find or create the <Children> container inside the parent <BinderItem>
        children_elem = parent_elem.find("Children")
        if children_elem is None:
            children_elem = ET.SubElement(parent_elem, "Children")
        parent_container = children_elem
        
    # Create the new <BinderItem>
    new_item = ET.Element("BinderItem", {
        "UUID": new_uuid,
        "Type": new_item_type,
        "Created": now_str,
        "Modified": now_str
    })
    
    # Create child nodes inside <BinderItem>
    title_elem = ET.SubElement(new_item, "Title")
    title_elem.text = new_item_title
    
    meta_elem = ET.SubElement(new_item, "MetaData")
    inc_compile = ET.SubElement(meta_elem, "IncludeInCompile")
    inc_compile.text = "Yes"
    
    text_settings = ET.SubElement(new_item, "TextSettings")
    text_select = ET.SubElement(text_settings, "TextSelection")
    text_select.text = "0,0"
    
    # Insert at position or append
    if position >= 0 and position < len(parent_container):
        parent_container.insert(position, new_item)
    else:
        parent_container.append(new_item)
        
    # Save the updated XML
    write_scrivx(tree, scrivx_path)
    
    # If the inserted item is of Type="Text", automatically ensure the basic file structures
    # (especially the required content.rtf) are generated on disk to prevent loading failures.
    if new_item_type == "Text":
        project_path = os.path.dirname(scrivx_path)
        save_scene_files(project_path, new_uuid, text="", notes="", synopsis="")
        
    return new_uuid

def update_binder_item_meta(scrivx_path: str, item_uuid: str, new_title: str = None) -> bool:
    """Updates metadata (like Title or Modified timestamp) in the .scrivx XML."""
    ET.register_namespace('', '')
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    item = find_binder_item_element(root, item_uuid)
    if item is None:
        return False
        
    import time
    tz = time.strftime("%z")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + tz
    item.attrib["Modified"] = now_str
    
    if new_title is not None:
        title_elem = item.find("Title")
        if title_elem is None:
            title_elem = ET.SubElement(item, "Title")
        title_elem.text = new_title
        
    write_scrivx(tree, scrivx_path)
    return True

def delete_binder_item_element(scrivx_path: str, item_uuid: str, soft_delete: bool = True) -> bool:
    """Removes a BinderItem from the XML. If soft_delete is True, moves it to the TrashFolder."""
    ET.register_namespace('', '')
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    parent_container, child_elem = find_parent_element(root, item_uuid)
    if child_elem is None:
        return False
        
    if soft_delete:
        # Find the TrashFolder
        trash_folder = None
        for item in root.iter("BinderItem"):
            if item.attrib.get("Type") == "TrashFolder":
                trash_folder = item
                break
                
        if trash_folder is not None:
            # Check if TrashFolder has <Children>
            trash_children = trash_folder.find("Children")
            if trash_children is None:
                trash_children = ET.SubElement(trash_folder, "Children")
            
            # Remove from original parent container and append to trash children
            parent_container.remove(child_elem)
            trash_children.append(child_elem)
        else:
            parent_container.remove(child_elem)
    else:
        parent_container.remove(child_elem)
        
    write_scrivx(tree, scrivx_path)
    return True

def get_scene_files(project_path: str, item_uuid: str) -> SceneFiles:
    """Reads Scrivener files for a given UUID and converts RTF content to plain text."""
    data_dir = os.path.join(project_path, "Files", "Data", item_uuid)
    
    result = {
        "text": "",
        "notes": "",
        "synopsis": ""
    }
    
    if not os.path.exists(data_dir):
        return SceneFiles(text="", notes="", synopsis="")
        
    # Read content.rtf
    from mcp_server.rtf_utils import rtf_to_markdown
    content_rtf_path = os.path.join(data_dir, "content.rtf")
    if os.path.exists(content_rtf_path):
        try:
            with open(content_rtf_path, "r", encoding="utf-8", errors="ignore") as f:
                rtf_data = f.read()
                result["text"] = rtf_to_markdown(rtf_data)
        except Exception as e:
            result["text"] = f"[Error reading content.rtf: {e}]"
            
    # Read notes.rtf
    notes_rtf_path = os.path.join(data_dir, "notes.rtf")
    if os.path.exists(notes_rtf_path):
        try:
            with open(notes_rtf_path, "r", encoding="utf-8", errors="ignore") as f:
                rtf_data = f.read()
                result["notes"] = rtf_to_markdown(rtf_data)
        except Exception as e:
            result["notes"] = f"[Error reading notes.rtf: {e}]"
            
    # Read synopsis.txt
    synopsis_path = os.path.join(data_dir, "synopsis.txt")
    if os.path.exists(synopsis_path):
        try:
            with open(synopsis_path, "r", encoding="utf-8", errors="ignore") as f:
                result["synopsis"] = f.read().strip()
        except Exception as e:
            result["synopsis"] = f"[Error reading synopsis.txt: {e}]"
            
    return SceneFiles(
        text=result["text"],
        notes=result["notes"],
        synopsis=result["synopsis"]
    )

def save_scene_files(project_path: str, item_uuid: str, text: str = None, notes: str = None, synopsis: str = None) -> bool:
    """Saves Scrivener files for a given UUID, converting plain text back to RTF as required."""
    data_dir = os.path.join(project_path, "Files", "Data", item_uuid)
    os.makedirs(data_dir, exist_ok=True)
    
    from mcp_server.rtf_utils import text_to_rtf
    if text is not None:
        content_rtf_path = os.path.join(data_dir, "content.rtf")
        rtf_data = text_to_rtf(text)
        with open(content_rtf_path, "w", encoding="utf-8") as f:
            f.write(rtf_data)
            
    if notes is not None:
        notes_rtf_path = os.path.join(data_dir, "notes.rtf")
        rtf_data = text_to_rtf(notes)
        with open(notes_rtf_path, "w", encoding="utf-8") as f:
            f.write(rtf_data)
            
    if synopsis is not None:
        synopsis_path = os.path.join(data_dir, "synopsis.txt")
        with open(synopsis_path, "w", encoding="utf-8") as f:
            f.write(synopsis.strip())
            
    return True

def create_new_project_folders(target_dir: str, name: str) -> str:
    """Creates a brand new .scriv project package from scratch."""
    if not name.endswith(".scriv"):
        project_name = name
        package_name = name + ".scriv"
    else:
        project_name = name[:-6]
        package_name = name
        
    project_path = os.path.join(target_dir, package_name)
    if os.path.exists(project_path):
        raise FileExistsError(f"Project already exists at {project_path}")
        
    # Create directories
    os.makedirs(project_path, exist_ok=True)
    os.makedirs(os.path.join(project_path, "Files", "Data"), exist_ok=True)
    os.makedirs(os.path.join(project_path, "Settings"), exist_ok=True)
    os.makedirs(os.path.join(project_path, "Snapshots"), exist_ok=True)
    
    # Generate default UUIDs
    draft_uuid = str(uuid.uuid4()).upper()
    chars_uuid = str(uuid.uuid4()).upper()
    places_uuid = str(uuid.uuid4()).upper()
    notes_uuid = str(uuid.uuid4()).upper()
    research_uuid = str(uuid.uuid4()).upper()
    trash_uuid = str(uuid.uuid4()).upper()
    
    import time
    tz = time.strftime("%z")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + tz
    
    # Construct base scrivx content
    scrivx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ScrivenerProject Identifier="{str(uuid.uuid4()).upper()}" Version="2.0" Creator="SCRMAC-3.5.2-17487" Device="Jenss-MacBook-Pro-3" Author="" Modified="{now_str}">
    <Binder>
        <BinderItem UUID="{draft_uuid}" Type="{TYPE_DRAFT_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_MANUSCRIPT}</Title>
            <Children/>
        </BinderItem>
        <BinderItem UUID="{chars_uuid}" Type="{TYPE_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_CHARACTERS}</Title>
            <MetaData>
                <IconFileName>Characters (Photo)</IconFileName>
            </MetaData>
            <Children/>
        </BinderItem>
        <BinderItem UUID="{places_uuid}" Type="{TYPE_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_PLACES}</Title>
            <MetaData>
                <IconFileName>Locations (Map)</IconFileName>
            </MetaData>
            <Children/>
        </BinderItem>
        <BinderItem UUID="{notes_uuid}" Type="{TYPE_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_NOTES}</Title>
            <MetaData>
                <IconFileName>Notes (Yellow Notepad)</IconFileName>
            </MetaData>
            <Children/>
        </BinderItem>
        <BinderItem UUID="{research_uuid}" Type="{TYPE_RESEARCH_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_RESEARCH}</Title>
            <Children/>
        </BinderItem>
        <BinderItem UUID="{trash_uuid}" Type="{TYPE_TRASH_FOLDER}" Created="{now_str}" Modified="{now_str}">
            <Title>{FOLDER_TRASH}</Title>
            <Children/>
        </BinderItem>
    </Binder>
</ScrivenerProject>
"""
    
    scrivx_path = os.path.join(project_path, f"{project_name}.scrivx")
    with open(scrivx_path, "w", encoding="utf-8") as f:
        f.write(scrivx_content)
        
    return project_path

def clone_project_structure(source_project_path: str, target_dir: str, new_book_name: str, copy_synopses: bool = True) -> str:
    """Clones the hierarchical structure of an existing Scrivener project into a new blank project."""
    source_scrivx = find_scrivx_path(source_project_path)
    
    # 1. Create a blank project with default base folders (generates a valid .scriv and base XML)
    new_project_path = create_new_project_folders(target_dir, new_book_name)
    new_scrivx = find_scrivx_path(new_project_path)
    
    # 2. Parse the source binder
    ET.register_namespace('', '')
    source_tree = ET.parse(source_scrivx)
    source_root = source_tree.getroot()
    source_binder = source_root.find("Binder")
    if source_binder is None:
        raise ValueError("Invalid source Scrivener project: no <Binder> found.")
        
    uuid_mapping = {}
    
    new_tree = ET.parse(new_scrivx)
    new_root = new_tree.getroot()
    new_binder = new_root.find("Binder")
    if new_binder is not None:
        # Clear the default top-level binder items from the newly created template
        new_binder.clear()
        
    import time
    tz = time.strftime("%z")
    
    def clone_element(elem: ET.Element, parent_new_element: ET.Element):
        if elem.tag != "BinderItem":
            return
            
        old_uuid = elem.attrib.get("UUID")
        new_uuid = str(uuid.uuid4()).upper()
        uuid_mapping[old_uuid] = new_uuid
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + tz
        
        # Create a new BinderItem replicating properties
        new_item = ET.SubElement(parent_new_element, "BinderItem", {
            "UUID": new_uuid,
            "Type": elem.attrib.get("Type", "Text"),
            "Created": now_str,
            "Modified": now_str
        })
        
        # Copy elements like Title, MetaData, TextSettings
        title_elem = elem.find("Title")
        if title_elem is not None:
            new_title = ET.SubElement(new_item, "Title")
            new_title.text = title_elem.text
            
        meta_elem = elem.find("MetaData")
        if meta_elem is not None:
            new_meta = ET.SubElement(new_item, "MetaData")
            for child in meta_elem:
                new_meta.append(ET.fromstring(ET.tostring(child)))
                
        text_settings = elem.find("TextSettings")
        if text_settings is not None:
            new_item.append(ET.fromstring(ET.tostring(text_settings)))
            
        # Create directories and files for the new scene/document
        if elem.attrib.get("Type") == "Text":
            text_val = ""
            notes_val = ""
            synopsis_val = ""
            
            if copy_synopses:
                old_files = get_scene_files(source_project_path, old_uuid)
                notes_val = old_files.get("notes", "")
                synopsis_val = old_files.get("synopsis", "")
                
            save_scene_files(new_project_path, new_uuid, text=text_val, notes=notes_val, synopsis=synopsis_val)
        
        # Recursively copy children
        children_elem = elem.find("Children")
        if children_elem is not None:
            new_children_container = ET.SubElement(new_item, "Children")
            for child in children_elem.findall("BinderItem"):
                clone_element(child, new_children_container)
                
    # Clone all top-level binder items from source
    for item in source_binder.findall("BinderItem"):
        clone_element(item, new_binder)
        
    # Write the updated XML
    write_scrivx(new_tree, new_scrivx)
    
    return new_project_path

def create_project_from_schema(target_dir: str, book_name: str, schema: list) -> str:
    """Creates a new Scrivener project populated with a hierarchical folder and scene outline schema."""
    # 1. Create base project
    project_path = create_new_project_folders(target_dir, book_name)
    scrivx_path = find_scrivx_path(project_path)
    
    # 2. Parse the newly created binder to locate the Manuscript (DraftFolder) root
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    draft_uuid = None
    for item in root.iter("BinderItem"):
        if item.attrib.get("Type") == "DraftFolder":
            draft_uuid = item.attrib.get("UUID")
            break
            
    if draft_uuid is None:
        raise ValueError("Could not find DraftFolder in the newly initialized Scrivener project.")
        
    # Helper to recursively insert schema items
    def insert_schema_items(items: list, parent_uuid: str):
        for item_data in items:
            title = item_data.get("title", "Untitled")
            item_type = item_data.get("type", "Text")
            synopsis = item_data.get("synopsis", "")
            notes = item_data.get("notes", "")
            
            # Insert item in XML binder structure
            new_uuid = insert_binder_item(scrivx_path, parent_uuid, title, item_type)
            
            # Save files if it's a Text document
            if item_type == "Text":
                save_scene_files(project_path, new_uuid, text="", notes=notes, synopsis=synopsis)
            
            # Recursively insert children
            children = item_data.get("children", [])
            if children:
                insert_schema_items(children, new_uuid)
                
    # 3. Insert the top-level schema items under Manuscript
    insert_schema_items(schema, draft_uuid)
    
    return project_path

def create_agent_workspace(project_path: str, folder_name: str = FOLDER_AGENT_WORKSPACE) -> str:
    """Initializes or retrieves a Scrivener-native agent workspace folder inside the binder."""
    scrivx_path = find_scrivx_path(project_path)
    
    # 1. Parse binder to check if the workspace folder already exists
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    workspace_uuid = None
    for item in root.iter("BinderItem"):
        if item.attrib.get("Type") == TYPE_FOLDER:
            title_elem = item.find("Title")
            if title_elem is not None and title_elem.text == folder_name:
                workspace_uuid = item.attrib.get("UUID")
                break
                
    if workspace_uuid is not None:
        return workspace_uuid
        
    # 2. Workspace folder doesn't exist, create it at the root level of Binder (parent_uuid="")
    workspace_uuid = insert_binder_item(scrivx_path, parent_uuid="", new_item_title=folder_name, new_item_type=TYPE_FOLDER)
    
    # Set a custom icon so it stands out visually inside Scrivener
    ET.register_namespace('', '')
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    folder_elem = find_binder_item_element(root, workspace_uuid)
    if folder_elem is not None:
        meta_elem = folder_elem.find("MetaData")
        if meta_elem is None:
            meta_elem = ET.SubElement(folder_elem, "MetaData")
        icon_elem = ET.SubElement(meta_elem, "IconFileName")
        icon_elem.text = "Notes (Blue Notepad)"
        
        write_scrivx(tree, scrivx_path)
        
    # 3. Create standard workspace files and folders
    # First, create Prompt Directives
    prompt_directives_text = load_template(TEMPLATE_PROMPT_DIRECTIVES)
    directives_uuid = insert_binder_item(scrivx_path, workspace_uuid, DOC_PROMPT_DIRECTIVES, TYPE_TEXT)
    save_scene_files(project_path, directives_uuid, text=prompt_directives_text, notes="", synopsis="AI steering instructions and style guide.")
    
    # Second, create Session Memory
    session_memory_template = load_template(TEMPLATE_SESSION_MEMORY)
    session_memory_text = session_memory_template.replace("{last_sync}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    memory_uuid = insert_binder_item(scrivx_path, workspace_uuid, DOC_SESSION_MEMORY, TYPE_TEXT)
    save_scene_files(project_path, memory_uuid, text=session_memory_text, notes="", synopsis="AI agent's persistent memory and history log.")
    
    # Third, create Task Checklist
    task_checklist_text = load_template(TEMPLATE_TASK_CHECKLIST)
    checklist_uuid = insert_binder_item(scrivx_path, workspace_uuid, DOC_TASK_CHECKLIST, TYPE_TEXT)
    save_scene_files(project_path, checklist_uuid, text=task_checklist_text, notes="", synopsis="Current task list and milestone progress tracking.")
    
    # Fourth, create the Codex folder
    codex_folder_uuid = insert_binder_item(scrivx_path, workspace_uuid, FOLDER_CODEX, TYPE_FOLDER)
    
    # Customise the Codex folder icon to stand out
    ET.register_namespace('', '')
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    codex_elem = find_binder_item_element(root, codex_folder_uuid)
    if codex_elem is not None:
        meta_elem = codex_elem.find("MetaData")
        if meta_elem is None:
            meta_elem = ET.SubElement(codex_elem, "MetaData")
        icon_elem = ET.SubElement(meta_elem, "IconFileName")
        icon_elem.text = "Research (Magnifying Glass)"
        write_scrivx(tree, scrivx_path)
        
    # Fifth, create Codex Sub-folders: Characters, Places, Lore & Factions
    # Characters Sub-folder
    chars_sub_uuid = insert_binder_item(scrivx_path, codex_folder_uuid, FOLDER_CHARACTERS, TYPE_FOLDER)
    
    char_template_text = load_template(TEMPLATE_CHAR_BODY)
    char_template_notes = load_template(TEMPLATE_CHAR_NOTES)
    char_template_uuid = insert_binder_item(scrivx_path, chars_sub_uuid, DOC_CHAR_TEMPLATE, TYPE_TEXT)
    save_scene_files(project_path, char_template_uuid, text=char_template_text, notes=char_template_notes, synopsis="Standard blueprint for character files.")
    
    # Places Sub-folder
    places_sub_uuid = insert_binder_item(scrivx_path, codex_folder_uuid, FOLDER_PLACES, TYPE_FOLDER)
    
    place_template_text = load_template(TEMPLATE_PLACE_BODY)
    place_template_notes = load_template(TEMPLATE_PLACE_NOTES)
    place_template_uuid = insert_binder_item(scrivx_path, places_sub_uuid, DOC_PLACE_TEMPLATE, TYPE_TEXT)
    save_scene_files(project_path, place_template_uuid, text=place_template_text, notes=place_template_notes, synopsis="Standard blueprint for setting files.")
    
    # Lore & Factions Sub-folder
    lore_sub_uuid = insert_binder_item(scrivx_path, codex_folder_uuid, FOLDER_LORE_FACTIONS, TYPE_FOLDER)
    
    lore_template_text = load_template(TEMPLATE_LORE_BODY)
    lore_template_notes = load_template(TEMPLATE_LORE_NOTES)
    lore_template_uuid = insert_binder_item(scrivx_path, lore_sub_uuid, DOC_LORE_TEMPLATE, TYPE_TEXT)
    save_scene_files(project_path, lore_template_uuid, text=lore_template_text, notes=lore_template_notes, synopsis="Standard blueprint for lore, magic systems, factions, or items.")
    
    return workspace_uuid

def search_project(project_path: str, query: str) -> list:
    """Searches for a query case-insensitively across all scene text, notes, and synopses in the project.
    Returns a list of dictionaries with matching item details and matches."""
    scrivx_path = find_scrivx_path(project_path)
    outline = parse_binder(scrivx_path)
    
    results = []
    query_lower = query.lower()
    
    def search_item(item: dict):
        item_uuid = item.get("uuid")
        item_type = item.get("type")
        item_title = item.get("title", "Untitled")
        
        if item_type == "Text":
            files_data = get_scene_files(project_path, item_uuid)
            text = files_data.get("text", "")
            notes = files_data.get("notes", "")
            synopsis = files_data.get("synopsis", "")
            
            matches = {}
            
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
                        
                    matches[field_name] = {
                        "count": field_text.lower().count(query_lower),
                        "snippet": snippet
                    }
            
            find_matches_in_field(text, "text")
            find_matches_in_field(notes, "notes")
            find_matches_in_field(synopsis, "synopsis")
            
            if matches:
                results.append({
                    "uuid": item_uuid,
                    "title": item_title,
                    "matches": matches
                })
                
        for child in item.get("children", []):
            search_item(child)
            
    for top_level in outline:
        search_item(top_level)
        
    return results

def compile_manuscript(project_path: str) -> str:
    """Compiles the entire Manuscript (DraftFolder) folder hierarchy into a unified Markdown draft."""
    scrivx_path = find_scrivx_path(project_path)
    
    # Parse XML
    tree = ET.parse(scrivx_path)
    root = tree.getroot()
    
    # Find DraftFolder
    draft_folder = None
    for item in root.iter("BinderItem"):
        if item.attrib.get("Type") == "DraftFolder":
            draft_folder = item
            break
            
    if draft_folder is None:
        raise ValueError("Could not find Manuscript (DraftFolder) in this Scrivener project.")
        
    compiled_parts = []
    
    def traverse_compile(elem: ET.Element, depth: int = 1):
        if elem.tag != "BinderItem":
            return
            
        item_uuid = elem.attrib.get("UUID")
        item_type = elem.attrib.get("Type")
        
        include_in_compile = True
        meta = elem.find("MetaData")
        if meta is not None:
            inc = meta.find("IncludeInCompile")
            if inc is not None and inc.text == "No":
                include_in_compile = False
                
        if not include_in_compile:
            return
            
        title = ""
        title_elem = elem.find("Title")
        if title_elem is not None:
            title = title_elem.text or ""
            
        if item_type == "Folder":
            header_char = "#" * min(depth + 1, 6)
            compiled_parts.append(f"\n{header_char} {title}\n")
            
        elif item_type == "Text":
            files_data = get_scene_files(project_path, item_uuid)
            text_content = files_data.get("text", "").strip()
            
            if text_content:
                scene_header_char = "#" * min(depth + 2, 6)
                compiled_parts.append(f"\n{scene_header_char} {title}\n")
                compiled_parts.append(text_content)
                compiled_parts.append("")
                
        children_elem = elem.find("Children")
        if children_elem is not None:
            for child in children_elem.findall("BinderItem"):
                traverse_compile(child, depth + 1)
                
    children_elem = draft_folder.find("Children")
    if children_elem is not None:
        for child in children_elem.findall("BinderItem"):
            traverse_compile(child, depth=1)
            
    return "\n".join(compiled_parts).strip()

def find_closest_match(text: str, target: str) -> tuple[str, float]:
    """Finds the substring in text that is most similar to target using difflib."""
    import difflib
    if not text or not target:
        return "", 0.0
        
    matcher = difflib.SequenceMatcher(None, text, target)
    matching_blocks = matcher.get_matching_blocks()
    valid_blocks = [b for b in matching_blocks if b.size > 0]
    
    if not valid_blocks:
        return "", 0.0
        
    groups = []
    current_group = []
    
    for block in valid_blocks:
        if not current_group:
            current_group.append(block)
        else:
            last_block = current_group[-1]
            gap_a = block.a - (last_block.a + last_block.size)
            if gap_a < len(target) + 100:
                current_group.append(block)
            else:
                groups.append(current_group)
                current_group = [block]
    if current_group:
        groups.append(current_group)
        
    best_match = ""
    best_score = -1.0
    
    for group in groups:
        first = group[0]
        last = group[-1]
        
        min_a = first.a
        min_b = first.b
        max_a = last.a + last.size
        max_b = last.b + last.size
        
        start = max(0, min_a - min_b)
        end = min(len(text), max_a + (len(target) - max_b))
        
        candidate = text[start:end]
        if not candidate:
            continue
            
        score = difflib.SequenceMatcher(None, candidate, target).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate
            
    return best_match, best_score

def patch_scene(project_path: str, uuid: str, target_text: str, replacement_text: str) -> bool:
    """Performs a targeted, safe search-and-replace edit on a specific scene by UUID.
    Supports exact matching, wildcard ellipsis matching (using '...' or '…'), and returns 
    helpful fuzzy match suggestions if target_text is not found."""
    import re
    scene_files = get_scene_files(project_path, uuid)
    text = scene_files.get("text", "")
    
    if not text:
        raise ValueError(f"Scene with UUID {uuid} has no story text content to patch.")
        
    # 1. Try Exact Match
    count = text.count(target_text)
    if count == 1:
        updated_text = text.replace(target_text, replacement_text)
        save_scene_files(project_path, uuid, text=updated_text)
        return True
    elif count > 1:
        raise ValueError(
            f"Target text was found {count} times in scene {uuid}. "
            "The edit is ambiguous. Please make the target_text more specific."
        )
        
    # 2. Try Wildcard/Ellipsis Match
    normalized_target = target_text.replace('…', '...')
    if '...' in normalized_target:
        parts = normalized_target.split('...')
        cleaned_parts = [p for p in parts if p]
        if cleaned_parts:
            pattern_str = r"[\s\S]*?".join(re.escape(p) for p in cleaned_parts)
            matches = list(re.finditer(pattern_str, text))
            if len(matches) == 1:
                match = matches[0]
                start, end = match.start(), match.end()
                updated_text = text[:start] + replacement_text + text[end:]
                save_scene_files(project_path, uuid, text=updated_text)
                return True
            elif len(matches) > 1:
                raise ValueError(
                    f"Target text pattern with wildcards was found {len(matches)} times in scene {uuid}. "
                    "The edit is ambiguous. Please make the target_text more specific."
                )

    # 3. Handle failure: find closest match to suggest
    closest_sub, similarity = find_closest_match(text, target_text)
    msg = f"Target text was not found in scene {uuid}. Cannot perform patch."
    if closest_sub and similarity >= 0.7:
        msg += f"\n\nDid you mean (similarity {similarity * 100:.1f}%):\n{closest_sub}"
        
    raise ValueError(msg)


def create_scene_snapshot(project_path: str, scene_uuid: str, description: str = "Before AI Edit") -> bool:
    """Creates a native, Scrivener-compliant snapshot of the current scene state."""
    import shutil
    import time
    import xml.etree.ElementTree as ET
    from datetime import datetime
    
    from mcp_server.rtf_utils import rtf_to_text
    # Paths
    data_dir = os.path.join(project_path, "Files", "Data", scene_uuid)
    content_rtf_path = os.path.join(data_dir, "content.rtf")
    
    if not os.path.exists(content_rtf_path):
        # Nothing to snapshot
        return False
        
    snapshots_dir = os.path.join(project_path, "Snapshots")
    # Correct Scrivener 3 folder extension: .snapshots
    scene_snapshots_dir = os.path.join(snapshots_dir, f"{scene_uuid}.snapshots")
    os.makedirs(scene_snapshots_dir, exist_ok=True)
    
    # Timestamps
    tz = time.strftime("%z")
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S") + " " + tz
    
    # Filename ID (derived by replacing spaces and colons in date_str with dashes)
    id_str = date_str.replace(" ", "-").replace(":", "-")
    
    # Ensure unique filename
    snapshot_rtf_path = os.path.join(scene_snapshots_dir, f"{id_str}.rtf")
    counter = 1
    while os.path.exists(snapshot_rtf_path):
        id_str = date_str.replace(" ", "-").replace(":", "-") + f"-{counter}"
        snapshot_rtf_path = os.path.join(scene_snapshots_dir, f"{id_str}.rtf")
        counter += 1
        
    # Copy content.rtf to snapshot file
    shutil.copy2(content_rtf_path, snapshot_rtf_path)
    
    # 1. Update index.xml
    index_xml_path = os.path.join(scene_snapshots_dir, "index.xml")
    
    ET.register_namespace('', '')
    if os.path.exists(index_xml_path):
        try:
            tree = ET.parse(index_xml_path)
            root = tree.getroot()
        except Exception:
            # Corrupt XML, reconstruct
            root = ET.Element("Snapshots", {"Version": "1.0"})
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("Snapshots", {"Version": "1.0"})
        tree = ET.ElementTree(root)
        
    # Create new <Snapshot> element (no attributes)
    snapshot_elem = ET.Element("Snapshot")
    title_elem = ET.SubElement(snapshot_elem, "Title")
    title_elem.text = description
    date_elem = ET.SubElement(snapshot_elem, "Date")
    date_elem.text = date_str
    
    root.append(snapshot_elem)
    
    # Format and save
    ET.indent(tree, space="    ")
    tree.write(index_xml_path, encoding="utf-8", xml_declaration=True)
    
    # 2. Update snapshot.indexes XML file
    snapshot_indexes_path = os.path.join(scene_snapshots_dir, "snapshot.indexes")
    
    with open(content_rtf_path, "r", encoding="utf-8", errors="ignore") as f:
        rtf_content = f.read()
    plain_text = rtf_to_text(rtf_content)
    
    if os.path.exists(snapshot_indexes_path):
        try:
            idx_tree = ET.parse(snapshot_indexes_path)
            idx_root = idx_tree.getroot()
        except Exception:
            idx_root = ET.Element("SnapshotIndexes", {"Version": "1.0", "BinderUUID": scene_uuid})
            idx_tree = ET.ElementTree(idx_root)
    else:
        idx_root = ET.Element("SnapshotIndexes", {"Version": "1.0", "BinderUUID": scene_uuid})
        idx_tree = ET.ElementTree(idx_root)
        
    idx_elem = ET.Element("Snapshot", {
        "Date": date_str
    })
    idx_title = ET.SubElement(idx_elem, "Title")
    idx_title.text = description
    
    idx_text = ET.SubElement(idx_elem, "Text")
    idx_text.text = plain_text
    
    idx_root.append(idx_elem)
    
    ET.indent(idx_tree, space="    ")
    idx_tree.write(snapshot_indexes_path, encoding="utf-8", xml_declaration=True)
    
    return True


def revert_scene_to_last_snapshot(project_path: str, scene_uuid: str) -> dict:
    """Reverts the scene's current content.rtf to the latest snapshot's RTF content.
    Returns a dict with status and details, or raises Exception on failure.
    """
    import shutil
    import xml.etree.ElementTree as ET
    
    snapshots_dir = os.path.join(project_path, "Snapshots")
    scene_snapshots_dir = os.path.join(snapshots_dir, f"{scene_uuid}.snapshots")
    index_xml_path = os.path.join(scene_snapshots_dir, "index.xml")
    
    if not os.path.exists(index_xml_path):
        raise FileNotFoundError("No snapshots exist for this scene.")
        
    try:
        tree = ET.parse(index_xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"Could not parse snapshot index.xml: {e}")
        
    snapshots = root.findall("Snapshot")
    if not snapshots:
        raise ValueError("No snapshots listed in index.xml.")
        
    # Get the last snapshot
    last_snapshot = snapshots[-1]
    date_elem = last_snapshot.find("Date")
    title_elem = last_snapshot.find("Title")
    
    if date_elem is None or not date_elem.text:
        raise ValueError("Latest snapshot is missing a Date element.")
        
    date_str = date_elem.text
    title_str = title_elem.text if title_elem is not None else "Untitled"
    
    # Construct filename
    id_str = date_str.replace(" ", "-").replace(":", "-")
    snapshot_rtf_path = os.path.join(scene_snapshots_dir, f"{id_str}.rtf")
    
    if not os.path.exists(snapshot_rtf_path):
        raise FileNotFoundError(f"Snapshot RTF file not found: {snapshot_rtf_path}")
        
    # Overwrite the current content.rtf
    data_dir = os.path.join(project_path, "Files", "Data", scene_uuid)
    content_rtf_path = os.path.join(data_dir, "content.rtf")
    
    # Make sure target directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    # Copy snapshot back
    shutil.copy2(snapshot_rtf_path, content_rtf_path)
    
    return {
        "status": "success",
        "title": title_str,
        "date": date_str,
        "filename": f"{id_str}.rtf"
    }

def bulk_patch_scenes_core(
    project_path: str,
    target_text: str,
    replacement_text: str,
    scene_uuids: list = None,
    dry_run: bool = False,
    snapshot_label: str = None,
    snapshotted_uuids: set = None
) -> dict:
    """Applies exact string replacement across multiple scenes, replacing all occurrences per scene.
    Creates a snapshot backup once per modified scene if dry_run is False.
    """
    if scene_uuids is None:
        from mcp_server.macro_analyzer import get_manuscript_scenes
        scenes = get_manuscript_scenes(project_path)
        scene_uuids = [s["uuid"] for s in scenes]
        scene_map = {s["uuid"]: s["title"] for s in scenes}
    else:
        scene_map = {}
        try:
            binder = parse_binder(find_scrivx_path(project_path))
            def build_map(node):
                if node.get("uuid"):
                    scene_map[node["uuid"]] = node.get("title") or "Untitled"
                for child in node.get("children") or []:
                    build_map(child)
            for root_node in binder:
                build_map(root_node)
        except Exception:
            pass

    if snapshotted_uuids is None:
        snapshotted_uuids = set()

    total_scenes = len(scene_uuids)
    scenes_modified = 0
    scenes_skipped = 0
    details = []

    label = snapshot_label or f"Bulk Patch: {target_text[:20]} -> {replacement_text[:20]}"

    for scene_uuid in scene_uuids:
        title = scene_map.get(scene_uuid, "Untitled")
        try:
            files_data = get_scene_files(project_path, scene_uuid)
            text = files_data.get("text", "")
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
                    create_scene_snapshot(project_path, scene_uuid, label)
                    snapshotted_uuids.add(scene_uuid)
                
                updated_text = text.replace(target_text, replacement_text)
                save_scene_files(project_path, scene_uuid, text=updated_text)
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
        except Exception as e:
            scenes_skipped += 1
            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": 0,
                "modified": False,
                "status": f"Error: {str(e)}"
            })

    return {
        "total_scenes": total_scenes,
        "scenes_modified": scenes_modified,
        "scenes_skipped": scenes_skipped,
        "details": details
    }

def regex_patch_scenes_core(
    project_path: str,
    pattern: str,
    replacement: str,
    scene_uuids: list = None,
    dry_run: bool = False,
    snapshot_label: str = None,
    snapshotted_uuids: set = None
) -> dict:
    """Applies regex search-and-replace across multiple scenes, replacing all occurrences per scene.
    Creates a snapshot backup once per modified scene if dry_run is False.
    """
    import re
    if scene_uuids is None:
        from mcp_server.macro_analyzer import get_manuscript_scenes
        scenes = get_manuscript_scenes(project_path)
        scene_uuids = [s["uuid"] for s in scenes]
        scene_map = {s["uuid"]: s["title"] for s in scenes}
    else:
        scene_map = {}
        try:
            binder = parse_binder(find_scrivx_path(project_path))
            def build_map(node):
                if node.get("uuid"):
                    scene_map[node["uuid"]] = node.get("title") or "Untitled"
                for child in node.get("children") or []:
                    build_map(child)
            for root_node in binder:
                build_map(root_node)
        except Exception:
            pass

    if snapshotted_uuids is None:
        snapshotted_uuids = set()

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
        try:
            files_data = get_scene_files(project_path, scene_uuid)
            text = files_data.get("text", "")
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
                    create_scene_snapshot(project_path, scene_uuid, label)
                    snapshotted_uuids.add(scene_uuid)
                
                updated_text = regex.sub(replacement, text)
                save_scene_files(project_path, scene_uuid, text=updated_text)
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
        except Exception as e:
            scenes_skipped += 1
            details.append({
                "uuid": scene_uuid,
                "title": title,
                "matches_found": 0,
                "modified": False,
                "status": f"Error: {str(e)}"
            })

    return {
        "total_scenes": total_scenes,
        "scenes_modified": scenes_modified,
        "scenes_skipped": scenes_skipped,
        "details": details
    }

def is_scrivener_running() -> bool:
    """Robustly checks if Scrivener is running on the local macOS system."""
    import subprocess
    try:
        res = subprocess.run(["ps", "ax"], capture_output=True, text=True, errors="ignore")
        for line in res.stdout.splitlines():
            if "Scrivener.app" in line or "/Scrivener" in line:
                if "debug_scriv_check.py" not in line and "test_scriv_check.py" not in line:
                    return True
        return False
    except Exception:
        return False

class ScrivenerBookDb(BookDb):
    def __init__(self, project_path: str):
        self.project_path = os.path.expanduser(project_path)
        self.scrivx_path = find_scrivx_path(self.project_path)

    @classmethod
    def exists(cls, project_path: str) -> bool:
        try:
            find_scrivx_path(project_path)
            return True
        except Exception:
            return False

    @classmethod
    def ensure_safe_to_write(cls, project_path: str) -> None:
        if project_path:
            path_lower = project_path.lower()
            if "temp" in path_lower or "tmp" in path_lower or "/var/" in path_lower or "private" in path_lower:
                return
                
        if is_scrivener_running():
            raise RuntimeError(
                "Scrivener is currently running locally. "
                "Please close the Scrivener application completely before running any tool that modifies the project, "
                "to prevent Scrivener from overwriting your changes from its in-memory cache."
            )

    @classmethod
    def create_new(cls, target_dir: str, name: str) -> "ScrivenerBookDb":
        new_path = create_new_project_folders(target_dir, name)
        return cls(new_path)

    @classmethod
    def clone_structure(
        cls, 
        source_db: "BookDb", 
        target_dir: str, 
        new_name: str, 
        copy_synopses: bool = True
    ) -> "ScrivenerBookDb":
        if not isinstance(source_db, ScrivenerBookDb):
            raise NotImplementedError("Cloning structure is only supported from a Scrivener project.")
        new_path = clone_project_structure(source_db.project_path, target_dir, new_name, copy_synopses)
        return cls(new_path)

    @classmethod
    def create_from_schema(
        cls, 
        target_dir: str, 
        book_name: str, 
        schema: List[Dict[str, Any]]
    ) -> "ScrivenerBookDb":
        new_path = create_project_from_schema(target_dir, book_name, schema)
        return cls(new_path)

    def get_outline(self) -> List[BinderNode]:
        return parse_binder(self.scrivx_path)

    def create_binder_item(
        self, 
        parent_uuid: str, 
        title: str, 
        item_type: str = "Text", 
        position: int = -1
    ) -> str:
        return insert_binder_item(self.scrivx_path, parent_uuid, title, item_type, position)

    def update_binder_item_meta(
        self, 
        uuid: str, 
        title: Optional[str] = None
    ) -> bool:
        return update_binder_item_meta(self.scrivx_path, uuid, title)

    def delete_binder_item(
        self, 
        uuid: str, 
        soft_delete: bool = True
    ) -> bool:
        return delete_binder_item_element(self.scrivx_path, uuid, soft_delete)

    def read_scene(self, uuid: str) -> SceneFiles:
        return get_scene_files(self.project_path, uuid)

    def write_scene(
        self, 
        uuid: str, 
        text: Optional[str] = None, 
        notes: Optional[str] = None, 
        synopsis: Optional[str] = None
    ) -> bool:
        return save_scene_files(self.project_path, uuid, text, notes, synopsis)

    def compile_manuscript(self) -> str:
        return compile_manuscript(self.project_path)

    def create_agent_workspace(
        self, 
        folder_name: str = "[Agent Workspace]"
    ) -> str:
        return create_agent_workspace(self.project_path, folder_name)

    def search_project(self, query: str) -> List[Dict[str, Any]]:
        return search_project(self.project_path, query)

    def create_scene_snapshot(
        self, 
        scene_uuid: str, 
        description: str = "Before AI Edit"
    ) -> bool:
        return create_scene_snapshot(self.project_path, scene_uuid, description)

    def revert_scene_to_last_snapshot(self, scene_uuid: str) -> Dict[str, Any]:
        return revert_scene_to_last_snapshot(self.project_path, scene_uuid)

    def patch_scene(
        self, 
        uuid: str, 
        target_text: str, 
        replacement_text: str
    ) -> bool:
        return patch_scene(self.project_path, uuid, target_text, replacement_text)

    def bulk_patch_scenes(
        self,
        target_text: str,
        replacement_text: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        return bulk_patch_scenes_core(
            project_path=self.project_path,
            target_text=target_text,
            replacement_text=replacement_text,
            scene_uuids=scene_uuids,
            dry_run=dry_run,
            snapshot_label=snapshot_label,
            snapshotted_uuids=snapshotted_uuids
        )

    def regex_patch_scenes(
        self,
        pattern: str,
        replacement: str,
        scene_uuids: List[str],
        dry_run: bool = False,
        snapshot_label: Optional[str] = None,
        snapshotted_uuids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        return regex_patch_scenes_core(
            project_path=self.project_path,
            pattern=pattern,
            replacement=replacement,
            scene_uuids=scene_uuids,
            dry_run=dry_run,
            snapshot_label=snapshot_label,
            snapshotted_uuids=snapshotted_uuids
        )

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
        for idx, patch in enumerate(patches):
            p_type = patch.get("type")
            pattern = patch.get("pattern") or patch.get("target")
            replacement = patch.get("replacement")
            curr_uuids = scene_uuids if scene_uuids is not None else patch.get("scene_uuids", [])

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
        raise NotImplementedError("Images are not supported for Scrivener projects.")

    def copy_image_from_project(self, image_uuid: str, destination_path: str) -> None:
        raise NotImplementedError("Images are not supported for Scrivener projects.")

    def read_image_bytes(self, image_uuid: str) -> tuple[bytes, str]:
        raise NotImplementedError("Images are not supported for Scrivener projects.")

    def generate_kdp_cover(self, image_uuid: str, output_name: str) -> str:
        raise NotImplementedError("KDP cover generation is not supported for Scrivener projects.")



