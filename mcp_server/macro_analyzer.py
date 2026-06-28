import json

from mcp_server.prompt_loader import load_prompt


def get_manuscript_scenes(project_path: str) -> list[dict]:
    """
    Parses the Scrivener binder XML outline and traverses the Manuscript/DraftFolder
    depth-first to collect all scenes in binder order, respecting IncludeInCompile.
    """
    from mcp_server.engine.book_classes import BinderNode
    from mcp_server.engine.book_engine import get_book_db
    db = get_book_db(project_path)
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
        raise ValueError("Could not find Manuscript (DraftFolder) in this Scrivener project.")
        
    scenes = []
    
    def traverse(node: BinderNode, current_chapter_title: str = "Unassigned"):
        item_uuid = node.uuid
        item_type = node.type
        title = node.title
        include_in_compile = node.include_in_compile
        
        if not include_in_compile:
            return
            
        next_chapter_title = current_chapter_title
        if item_type == "Folder":
            next_chapter_title = title
            
        elif item_type == "Text":
            files_data = db.read_scene(item_uuid)
            text_content = files_data.text.strip()
            synopsis_content = files_data.synopsis.strip()
            if text_content:
                scenes.append({
                    "uuid": item_uuid,
                    "title": title,
                    "chapter": current_chapter_title,
                    "text": text_content,
                    "synopsis": synopsis_content
                })
                
        for child in node.children:
            traverse(child, next_chapter_title)
            
    # Traverse children of the draft root folder
    if draft_folder:
        for child in draft_folder.children:
            traverse(child)
            
    return scenes

def analyze_scene(
    scene: dict,
    scene_index: int,
    total_scenes: int,
    model_string: str,
    project_path: str,
    benchmarks: dict,
    style_directives: str,
    call_ai_fn,
    author_concerns: str = None,
    synopsis_doc: str = None
) -> dict:
    """
    Calls the LLM via call_ai_fn to analyze a single scene and extract structured SAC/timeline logs.
    """
    system_prompt = load_prompt("macro_analyze_scene_system.txt")

    user_prompt = (
        load_prompt("macro_analyze_scene_user.txt")
        .replace("{scene_index}", str(scene_index + 1))
        .replace("{total_scenes}", str(total_scenes))
        .replace("{chapter}", scene['chapter'])
        .replace("{title}", scene['title'])
        .replace("{synopsis}", scene['synopsis'] or 'None provided.')
        .replace("{scene_text}", scene['text'])
        .replace("{target_genre}", benchmarks.get('genre', 'General Fiction'))
        .replace("{style_directives}", style_directives or 'None')
    )

    if author_concerns:
        user_prompt += f"\nAuthor Concerns: {author_concerns}\n"
    if synopsis_doc:
        user_prompt += f"\nMaster Project Synopsis: {synopsis_doc}\n"

    raw_response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    
    raw_response = raw_response or ""
    # Strip markdown block wraps if the LLM ignored directives
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        # remove first line
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
        
    try:
        parsed = json.loads(cleaned)
        # Ensure chapter is retained
        parsed["chapter"] = scene["chapter"]
        parsed["uuid"] = scene["uuid"]
        return parsed
    except Exception as e:
        # Return fallback on JSON parse failure
        return {
            "uuid": scene["uuid"],
            "scene_title": scene["title"],
            "chapter": scene["chapter"],
            "outer_event": "JSON Parse Error on response: " + str(e),
            "writer_intent": {
                "goal": "Unknown",
                "friction": "Unknown",
                "change": "Unknown"
            },
            "thematic_takeaway": "Unknown",
            "subplots": [],
            "timeline": {
                "weekday": None,
                "timestamp": None,
                "weather": None,
                "injuries": None,
                "travel": None
            },
            "raw_error_response": raw_response
        }

def synthesize_macro_report(
    sac_data: list[dict],
    model_string: str,
    project_path: str,
    benchmarks: dict,
    style_directives: str,
    call_ai_fn,
    author_concerns: str = None,
    synopsis_doc: str = None
) -> tuple[str, str]:
    """
    Combines all scene-level records and calls the LLM to synthesize the Macro-Structural
    Assessment and the Open Issues List.
    """
    system_prompt = load_prompt("macro_synthesize_report_system.txt")

    # Convert SAC data to a compact summary to fit context limits
    compact_sac = []
    for idx, s in enumerate(sac_data):
        if not s:
            s = {}
        compact_sac.append(
            f"Scene {idx+1}: {s.get('chapter') or 'Chapter'} - {s.get('scene_title') or 'Scene'}\n"
            f"  Outer Event: {s.get('outer_event') or 'None'}\n"
            f"  Goal: {(s.get('writer_intent') or {}).get('goal') or 'None'}\n"
            f"  Friction: {(s.get('writer_intent') or {}).get('friction') or 'None'}\n"
            f"  Change: {(s.get('writer_intent') or {}).get('change') or 'None'}\n"
            f"  Takeaway: {s.get('thematic_takeaway') or 'None'}\n"
            f"  Subplots: {', '.join(s.get('subplots') or [])}\n"
            f"  Timeline: {json.dumps(s.get('timeline') or {})}\n"
        )
    
    user_prompt = (
        load_prompt("macro_synthesize_report_user.txt")
        .replace("{compact_sac}", "\n".join(compact_sac))
        .replace("{target_genre}", benchmarks.get('genre', 'General Fiction'))
        .replace("{style_directives}", style_directives or 'None')
    )

    if author_concerns:
        user_prompt += f"\nAuthor Concerns: {author_concerns}\n"
    if synopsis_doc:
        user_prompt += f"\nMaster Project Synopsis: {synopsis_doc}\n"

    response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    response = response or ""

    # Parse response into separate sections
    assessment_part = ""
    open_issues_part = ""

    assessment_marker = "=== MACRO-STRUCTURAL EDITORIAL ASSESSMENT ==="
    open_issues_marker = "=== OPEN ISSUES LIST ==="

    if assessment_marker in response and open_issues_marker in response:
        parts = response.split(open_issues_marker)
        open_issues_part = parts[1].strip()
        
        assessment_sub = parts[0].split(assessment_marker)
        assessment_part = assessment_sub[1].strip()
    else:
        # Fallback if LLM deviates from headers
        assessment_part = response
        open_issues_part = "Failed to separate reports dynamically. Please review the full assessment above."

    return assessment_part, open_issues_part


def simulate_ideal_reader_analysis(
    sac_data: list[dict],
    scenes: list[dict],
    persona_profile: str,
    author_concerns: str,
    genre_guide: str,
    model_string: str,
    project_path: str,
    benchmarks: dict,
    style_directives: str,
    call_ai_fn
) -> tuple[str, str]:
    """
    Simulates the 'Ideal Reader' persona on the manuscript to produce:
    1. Editorial Letter: high-level developmental audit.
    2. Inline Comments: anchored in-line developmental suggestions & positive reinforcement.
    """
    system_prompt = load_prompt("ideal_reader_system.txt")

    # Construct compact scene outline and full text for LLM context
    compact_sac = []
    for idx, s in enumerate(sac_data):
        if not s:
            s = {}
        compact_sac.append(
            f"Scene {idx+1}: {s.get('chapter') or 'Chapter'} - {s.get('scene_title') or 'Scene'} (UUID: {s.get('uuid')})\n"
            f"  Outer Event: {s.get('outer_event') or 'None'}\n"
            f"  Goal: {(s.get('writer_intent') or {}).get('goal') or 'None'}\n"
            f"  Friction: {(s.get('writer_intent') or {}).get('friction') or 'None'}\n"
            f"  Change: {(s.get('writer_intent') or {}).get('change') or 'None'}\n"
            f"  Takeaway: {s.get('thematic_takeaway') or 'None'}\n"
            f"  Subplots: {', '.join(s.get('subplots') or [])}\n"
        )
    sac_summary_str = "\n".join(compact_sac)

    manuscript_content = []
    for idx, s in enumerate(scenes):
        manuscript_content.append(
            f"=== Scene {idx+1}: {s['chapter']} - {s['title']} (UUID: {s['uuid']}) ===\n"
            f"Synopsis: {s['synopsis'] or 'None'}\n\n"
            f"{s['text']}\n"
        )
    manuscript_text = "\n".join(manuscript_content)

    user_prompt = (
        load_prompt("ideal_reader_user.txt")
        .replace("{persona_profile}", persona_profile or 'General reader.')
        .replace("{author_concerns}", author_concerns or 'Conduct a general developmental audit.')
        .replace("{genre_guide}", genre_guide or 'General fiction benchmarks.')
        .replace("{target_genre}", benchmarks.get('genre', 'General Fiction'))
        .replace("{style_directives}", style_directives or 'None')
        .replace("{sac_summary_str}", sac_summary_str)
        .replace("{manuscript_text}", manuscript_text)
    )

    response = call_ai_fn(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_string=model_string,
        project_path=project_path
    )
    response = response or ""

    editorial_letter = ""
    inline_comments_str = ""

    editorial_letter_marker = "=== EDITORIAL LETTER ==="
    inline_comments_marker = "=== INLINE COMMENTS ==="

    if editorial_letter_marker in response and inline_comments_marker in response:
        parts = response.split(inline_comments_marker)
        inline_comments_str = parts[1].strip()
        
        editorial_sub = parts[0].split(editorial_letter_marker)
        editorial_letter = editorial_sub[1].strip()
    else:
        # Fallback if markers are missing
        editorial_letter = response
        inline_comments_str = "[]"

    return editorial_letter, inline_comments_str
