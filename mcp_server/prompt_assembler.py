from mcp_server.book_codex import (
    format_codex_context_block,
    match_entities,
    parse_codex,
)
from mcp_server.engine.book_classes import BinderNode
from mcp_server.engine.book_engine import BookDb, get_book_db
from mcp_server.prompt_loader import load_prompt


def compile_manuscript_so_far(db: BookDb, target_uuid: str) -> str:
    """Compiles all scene text drafts preceding the target scene UUID in draft order."""
    binder_outline = db.get_outline()
    
    def find_draft_folder(nodes: list[BinderNode]) -> BinderNode | None:
        for n in nodes:
            if n.type == "DraftFolder":
                return n
            res = find_draft_folder(n.children)
            if res:
                return res
        return None
        
    draft_folder = find_draft_folder(binder_outline)
    if draft_folder is None:
        return ""
        
    compiled_parts = []
    reached_target = [False]
    
    def traverse(node: BinderNode, depth: int = 1):
        if reached_target[0]:
            return
            
        item_uuid = node.uuid
        item_type = node.type
        title = node.title
        include_in_compile = node.include_in_compile
        
        if item_uuid == target_uuid:
            reached_target[0] = True
            return
            
        if not include_in_compile:
            return
            
        if item_type == "Folder" and not reached_target[0]:
            header_char = "#" * min(depth + 1, 6)
            compiled_parts.append(f"\n{header_char} {title}\n")
            
        elif item_type == "Text" and not reached_target[0]:
            files_data = db.read_scene(item_uuid)
            text_content = files_data.text.strip()
            if text_content:
                scene_header_char = "#" * min(depth + 2, 6)
                compiled_parts.append(f"\n{scene_header_char} {title}\n")
                compiled_parts.append(text_content)
                compiled_parts.append("")
                
        for child in node.children:
            traverse(child, depth + 1)
            
    if draft_folder:
        for child in draft_folder.children:
            traverse(child, depth=1)
            
    return "\n".join(compiled_parts).strip()

def compile_writing_prompt(project_path: str, scene_uuid: str, current_act: str = None, custom_instructions: str = None) -> dict:
    """Gathers style guides, previous manuscript drafts, scene beats, and matching timeline Codex entries.
    Assembles them into a structured payload for LLM injection.
    """
    db = get_book_db(project_path)
    binder_outline = db.get_outline()
    
    # 1. Extract Prompt Directives (POV, style guide) from the workspace
    directives_text = ""
    agent_workspace = None
    for node in binder_outline:
        if "[agent workspace]" in node.get("title", "").lower():
            agent_workspace = node
            break
            
    if agent_workspace:
        pd_node = None
        for child in agent_workspace.get("children", []):
            if child.get("title", "").lower() == "prompt directives":
                pd_node = child
                break
        if pd_node:
            directives_text = db.read_scene(pd_node["uuid"]).text
            
    # Fallback to simple default if empty
    if not directives_text.strip():
        directives_text = "# Style Guide & Prompt Directives\n- POV: Third Person Limited\n- Tense: Past Tense"
        
    # 2. Compile all written manuscript preceding this scene
    manuscript_so_far = compile_manuscript_so_far(db, scene_uuid)
    
    # 3. Read current scene beats (synopsis) and draft-so-far
    scene_files = db.read_scene(scene_uuid)
    scene_beats = scene_files.synopsis.strip()
    scene_draft_so_far = scene_files.text.strip()
    
    # 4. Match Codex entries inside the scene beats and current scene draft
    codex_db = parse_codex(project_path, current_act=current_act)
    search_context = f"{scene_beats}\n{scene_draft_so_far}"
    matched_entries = match_entities(search_context, codex_db)
    codex_context_block = format_codex_context_block(matched_entries)
    
    # Assemble standard system instructions
    system_prompt = load_prompt("draft_system.txt").replace("{directives_text}", directives_text)
    
    # Assemble user prompt containing the massive continuous context
    user_prompt_parts = []
    
    if manuscript_so_far:
        user_prompt_parts.append(
            load_prompt("draft_user_continuity.txt").replace("{manuscript_so_far}", manuscript_so_far)
        )
        
    if codex_context_block:
        user_prompt_parts.append(codex_context_block + "\n")
        
    # Drafting objective
    objective_text = load_prompt("draft_user_objective.txt").replace(
        "{scene_beats}", 
        scene_beats if scene_beats else '[No synopsis beats provided. Continue the narrative naturally.]'
    )
    user_prompt_parts.append(objective_text)
    
    if scene_draft_so_far:
        user_prompt_parts.append(
            load_prompt("draft_user_draft_so_far.txt").replace("{scene_draft_so_far}", scene_draft_so_far)
        )
    else:
        user_prompt_parts.append(
            load_prompt("draft_user_draft_from_beginning.txt")
        )
        
    if custom_instructions:
        user_prompt_parts.append(
            load_prompt("draft_user_custom_instructions.txt").replace("{custom_instructions}", custom_instructions)
        )
        
    user_prompt = "\n".join(user_prompt_parts)
    
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "matched_entries_uuids": [e["uuid"] for e in matched_entries]
    }
