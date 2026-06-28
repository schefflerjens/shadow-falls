import re

from mcp_server.engine.book_engine import BookDb, get_book_db


def parse_section_tables(notes_text: str) -> dict:
    """Parses Markdown tables under headings in the notes text.
    Returns a dictionary mapping lowercase section headings to list of row dicts.
    """
    sections = {}
    if not notes_text:
        return sections
        
    current_section = "default"
    lines = [l.strip() for l in notes_text.split("\n")]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            # Update current section heading
            current_section = line.lstrip("#").strip().lower()
            i += 1
            continue
            
        # Check if a table starts at line i
        if line.startswith("|"):
            # Parse headers
            headers = [h.strip() for h in line.split("|")[1:-1]]
            # Check if next line is separator
            if i + 1 < len(lines) and lines[i+1].startswith("|") and ("---" in lines[i+1] or ":" in lines[i+1]):
                rows = []
                j = i + 2
                while j < len(lines) and lines[j].startswith("|"):
                    row_vals = [val.strip() for val in lines[j].split("|")[1:-1]]
                    if len(row_vals) < len(headers):
                        row_vals += [""] * (len(headers) - len(row_vals))
                    rows.append(dict(zip(headers, row_vals[:len(headers)])))
                    j += 1
                sections[current_section] = rows
                i = j
                continue
        i += 1
    return sections

def extract_metadata_from_table(table_rows: list) -> dict:
    """Helper to convert parsed attribute-value rows into a flat dict."""
    metadata = {}
    for row in table_rows:
        if not row:
            continue
        keys = list(row.keys())
        if len(keys) >= 2:
            attr = row.get(keys[0], "").strip()
            val = row.get(keys[1], "").strip()
            if attr:
                metadata[attr.lower()] = val
    return metadata

def parse_codex_entry(db: BookDb, uuid: str, title: str, category: str, location_path: list = None, current_act: str = None) -> dict:
    """Reads scene text and parses note Markdown tables for a single Codex entry, applying act overrides."""
    files_data = db.read_scene(uuid)
    text = files_data.text
    notes = files_data.notes
    synopsis = files_data.synopsis
    
    sections = parse_section_tables(notes)
    
    # Parse generic metadata table
    meta_table = next((rows for heading, rows in sections.items() if "metadata" in heading), [])
    metadata = extract_metadata_from_table(meta_table)
    
    # Extract clean aliases
    aliases_str = metadata.get("aliases") or metadata.get("alias") or ""
    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
    
    # Also include the entry title as the primary name
    all_names = [title] + aliases
    
    # Parse relationships table
    rel_table = next((rows for heading, rows in sections.items() if "relationship" in heading), [])
    relationships = []
    for row in rel_table:
        target = row.get("Target Entity (UUID or Name)") or row.get("Target") or ""
        rel_type = row.get("Relationship Type") or row.get("Type") or ""
        detail = row.get("Detail / Status") or row.get("Detail") or ""
        if target:
            relationships.append({
                "target": target.strip(),
                "type": rel_type.strip(),
                "detail": detail.strip()
            })
            
    # Parse Chronological overrides (spoiler management)
    timeline_table = next((rows for heading, rows in sections.items() if "chronological" in heading or "timeline" in heading), [])
    active_override = None
    if current_act and timeline_table:
        current_act_clean = current_act.lower().strip()
        for row in timeline_table:
            # Check act matching in columns
            act_col = row.get("Act / Chapter") or row.get("Act") or row.get("Timeline") or ""
            state_col = row.get("State Name") or row.get("State") or ""
            details_col = row.get("State Details & Overrides") or row.get("Overrides") or row.get("Details") or ""
            
            if act_col.lower().strip() == current_act_clean:
                active_override = {
                    "act": act_col.strip(),
                    "state": state_col.strip(),
                    "details": details_col.strip()
                }
                break
                
    # Compile final description (combining base text and current chronological overrides)
    summary_description = text
    if active_override:
        summary_description += f"\n\n**[Timeline Override - {active_override['act']} ({active_override['state']})]:** {active_override['details']}"
        
    return {
        "uuid": uuid,
        "title": title,
        "category": category,
        "aliases": aliases,
        "names": all_names,
        "text": text,
        "synopsis": synopsis,
        "notes": notes,
        "metadata": metadata,
        "relationships": relationships,
        "location_path": location_path or [],
        "active_override": active_override,
        "summary": summary_description
    }

def collect_binder_entries(db: BookDb, node: dict, category: str, path_prefix: list = None, current_act: str = None) -> list:
    """Recursively collects Codex entries from a binder outline node."""
    entries = []
    node_type = node.get("type")
    node_uuid = node.get("uuid")
    node_title = node.get("title", "")
    
    current_path = (path_prefix or []) + ([node_title] if node_type == "Folder" else [])
    
    if node_type == "Text" and "template" not in node_title.lower():
        # Clean location path (excluding root names like Places or Codex)
        clean_loc_path = [p for p in current_path if p.lower() not in ("places", "codex", "characters")]
        entry = parse_codex_entry(db, node_uuid, node_title, category, clean_loc_path, current_act)
        entries.append(entry)
        
    for child in node.get("children", []):
        entries.extend(collect_binder_entries(db, child, category, current_path, current_act))
        
    return entries

def parse_codex(project_path: str, current_act: str = None) -> dict:
    """Parses all characters, locations, and lore documents from standard binder locations and the agent workspace.
    Returns a unified codex dictionary grouped by category.
    """
    db = get_book_db(project_path)
    binder_outline = db.get_outline()
    
    codex_db = {
        "characters": [],
        "places": [],
        "lore": []
    }
    
    # 1. Look for standard top-level binders (Characters, Places)
    for root_node in binder_outline:
        title_lower = root_node.get("title", "").lower()
        if title_lower == "characters":
            codex_db["characters"].extend(collect_binder_entries(db, root_node, "character", current_act=current_act))
        elif title_lower == "places":
            codex_db["places"].extend(collect_binder_entries(db, root_node, "place", current_act=current_act))
            
    # 2. Look for [Agent Workspace] / Codex folder
    agent_workspace = None
    for root_node in binder_outline:
        if "[agent workspace]" in root_node.get("title", "").lower():
            agent_workspace = root_node
            break
            
    if agent_workspace:
        # Find Codex folder child
        codex_folder = None
        for child in agent_workspace.get("children", []):
            if child.get("title", "").lower() == "codex":
                codex_folder = child
                break
                
        if codex_folder:
            for category_folder in codex_folder.get("children", []):
                cat_title_lower = category_folder.get("title", "").lower()
                if "character" in cat_title_lower:
                    codex_db["characters"].extend(collect_binder_entries(db, category_folder, "character", current_act=current_act))
                elif "place" in cat_title_lower:
                    codex_db["places"].extend(collect_binder_entries(db, category_folder, "place", current_act=current_act))
                elif "lore" in cat_title_lower or "faction" in cat_title_lower:
                    codex_db["lore"].extend(collect_binder_entries(db, category_folder, "lore", current_act=current_act))
                    
    # Deduplicate entries by UUID (in case they appear in both top-level folders and the workspace folder)
    for key in codex_db:
        seen_uuids = set()
        deduped = []
        for entry in codex_db[key]:
            if entry["uuid"] not in seen_uuids:
                seen_uuids.add(entry["uuid"])
                deduped.append(entry)
        codex_db[key] = deduped
        
    return codex_db

def match_entities(text: str, codex_db: dict) -> list:
    """Scans text for mentions of character names, aliases, place names, or lore keywords.
    Returns a list of matched codex entry dicts.
    """
    if not text:
        return []
        
    matched = []
    text_lower = text.lower()
    
    # We collect all candidates across all groups
    all_candidates = codex_db["characters"] + codex_db["places"] + codex_db["lore"]
    
    for entry in all_candidates:
        match_found = False
        
        # Check every alias and name.
        # Use simple word boundary regex to avoid substring collisions (e.g. "Jim" matching "Jimmy" or "Cat" matching "Cathedral")
        for name in entry["names"]:
            name_escaped = re.escape(name.lower().strip())
            # Match if the name appears with word boundaries
            pattern = rf"\b{name_escaped}\b"
            if re.search(pattern, text_lower):
                match_found = True
                break
                
        if match_found:
            matched.append(entry)
            
    return matched

def format_codex_context_block(matched_entries: list) -> str:
    """Formats a list of matched codex entries into a clean Markdown block for LLM prompt injection."""
    if not matched_entries:
        return ""
        
    lines = ["## Active Lore & Codex References\n"]
    
    # Group by category
    by_category = {
        "character": [],
        "place": [],
        "lore": []
    }
    for entry in matched_entries:
        by_category[entry["category"]].append(entry)
        
    for cat, items in by_category.items():
        if not items:
            continue
            
        lines.append(f"### {cat.capitalize()}s")
        for item in items:
            title = item["title"]
            aliases = ", ".join(item["aliases"])
            aliases_str = f" (Aliases: {aliases})" if aliases else ""
            
            # Format spatial location for places
            loc_str = ""
            if cat == "place" and item.get("location_path"):
                loc_str = f" [Location Path: {' > '.join(item['location_path'])}]"
                
            # Core attributes from notes metadata
            meta_details = []
            for k, v in item["metadata"].items():
                if k not in ("aliases", "alias", "type", "parent location"):
                    meta_details.append(f"{k.capitalize()}: {v}")
            meta_str = f" | {', '.join(meta_details)}" if meta_details else ""
            
            # Relationships
            rel_details = []
            for r in item["relationships"]:
                rel_details.append(f"{r['type']} to {r['target']} ({r['detail']})")
            rel_str = f"\n  - **Relationships**: {'; '.join(rel_details)}" if rel_details else ""
            
            lines.append(f"- **{title}**{aliases_str}{loc_str}{meta_str}")
            # Insert summary (narrative prose + overrides if matching current_act)
            clean_summary = item["summary"].strip()
            if clean_summary:
                # Indent summary for visual clarity in prompt
                indented_summary = "\n  ".join(clean_summary.split("\n"))
                lines.append(f"  {indented_summary}")
            if rel_str:
                lines.append(rel_str)
            lines.append("")
            
    return "\n".join(lines).strip()
