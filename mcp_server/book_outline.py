from mcp_server.book_codex import match_entities
from mcp_server.engine.book_engine import get_book_db


def compile_full_outline(project_path: str, codex_db: dict = None) -> dict:
    """Traverses the Manuscript (DraftFolder) and compiles a structured plot model and Markdown representation.
    Lists which Codex entities appear in every chapter or scene synopsis.
    """
    db = get_book_db(project_path)
    binder_outline = db.get_outline()
    
    # Locate DraftFolder
    draft_folder = None
    for item in binder_outline:
        if item.get("type") == "DraftFolder":
            draft_folder = item
            break
            
    if not draft_folder:
        return {
            "flat_list": [],
            "markdown": "No Manuscript (DraftFolder) folder found in project binder."
        }
        
    flat_list = []
    markdown_lines = ["# Manuscript Plot Outline & Entity Track\n"]
    
    def traverse(node: dict, depth: int = 1):
        node_uuid = node.get("uuid")
        node_type = node.get("type")
        node_title = node.get("title", "Untitled")
        
        # Read synopsis and text
        files_data = db.read_scene(node_uuid)
        synopsis = files_data.synopsis.strip()
        
        # Match entities in synopsis
        matched_chars = []
        matched_places = []
        matched_lore = []
        if codex_db and synopsis:
            matches = match_entities(synopsis, codex_db)
            for m in matches:
                if m["category"] == "character":
                    matched_chars.append(m["title"])
                elif m["category"] == "place":
                    matched_places.append(m["title"])
                elif m["category"] == "lore":
                    matched_lore.append(m["title"])
                    
        flat_item = {
            "uuid": node_uuid,
            "title": node_title,
            "type": node_type,
            "synopsis": synopsis,
            "depth": depth,
            "characters": matched_chars,
            "places": matched_places,
            "lore": matched_lore
        }
        flat_list.append(flat_item)
        
        # Build Markdown line representation
        if node_type == "DraftFolder":
            # Don't add root draft folder header to markdown
            pass
        elif node_type == "Folder":
            header_char = "#" * min(depth + 1, 6)
            markdown_lines.append(f"\n{header_char} Chapter: {node_title} (UUID: {node_uuid})")
            if synopsis:
                markdown_lines.append(f"*Premise:* {synopsis}")
        elif node_type == "Text":
            header_char = "#" * min(depth + 2, 6)
            markdown_lines.append(f"\n{header_char} Scene: {node_title} (UUID: {node_uuid})")
            if synopsis:
                markdown_lines.append(f"*Beats:* {synopsis}")
            else:
                markdown_lines.append("*Beats:* [No scene beats planned yet]")
                
            # Add entity appearance tracks
            track_items = []
            if matched_chars:
                track_items.append(f"**Characters:** {', '.join(matched_chars)}")
            if matched_places:
                track_items.append(f"**Places:** {', '.join(matched_places)}")
            if matched_lore:
                track_items.append(f"**Lore/Factions:** {', '.join(matched_lore)}")
                
            if track_items:
                markdown_lines.append("  " + " | ".join(track_items))
                
        # Recursively traverse children
        for child in node.get("children", []):
            traverse(child, depth + 1)
            
    traverse(draft_folder, depth=0)
    
    return {
        "flat_list": flat_list,
        "markdown": "\n".join(markdown_lines).strip()
    }
