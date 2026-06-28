import html
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Optional

from mcp_server.book_codex import extract_metadata_from_table, parse_section_tables
from mcp_server.engine.book_engine import (
    TYPE_DRAFT_FOLDER,
    TYPE_FOLDER,
    TYPE_TEXT,
    BinderNode,
    BookDb,
)
from mcp_server.kdp_utils import is_kdp_compliant


def parse_inline_markdown(text: str) -> str:
    """Escapes HTML special characters and converts basic inline markdown (bold, italic, code) to XHTML."""
    escaped = html.escape(text)
    
    # Inline code: `code` -> <code>code</code>
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    
    # Bold ** or __
    escaped = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'__(.*?)__', r'<strong>\1</strong>', escaped)
    
    # Italic * or _
    escaped = re.sub(r'\*(.*?)\*', r'<em>\1</em>', escaped)
    escaped = re.sub(r'_(.*?)_', r'<em>\1</em>', escaped)
    
    return escaped


def markdown_to_xhtml(md_text: str) -> str:
    """Converts a scene's Markdown text block into XHTML-compliant body content."""
    # Normalize line endings
    md_text = md_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = md_text.split("\n")
    
    html_blocks = []
    current_para = []
    in_list = False
    in_blockquote = False
    in_code_block = False
    
    def flush_para():
        if current_para:
            text = "\n".join(current_para).strip()
            if text:
                html_blocks.append(f"<p>{parse_inline_markdown(text)}</p>")
            current_para.clear()
            
    for line in lines:
        stripped = line.strip()
        
        # Code block
        if stripped.startswith("```"):
            flush_para()
            if in_list:
                html_blocks.append("</ul>")
                in_list = False
            if in_blockquote:
                html_blocks.append("</blockquote>")
                in_blockquote = False
                
            in_code_block = not in_code_block
            continue
            
        if in_code_block:
            html_blocks.append(f"<pre><code>{html.escape(line)}</code></pre>")
            continue
            
        # Closing list if a non-list item is encountered
        if in_list and not (stripped.startswith("* ") or stripped.startswith("- ")):
            html_blocks.append("</ul>")
            in_list = False
            
        # Closing blockquote if a non-blockquote item is encountered
        if in_blockquote and not stripped.startswith(">"):
            html_blocks.append("</blockquote>")
            in_blockquote = False
            
        # Blank line handles paragraph separation
        if not stripped:
            flush_para()
            continue
            
        # Headers
        if stripped.startswith("#"):
            flush_para()
            level = 0
            while level < len(stripped) and stripped[level] == '#':
                level += 1
            header_text = stripped[level:].strip()
            # Bound header level between h1 and h6
            level_num = min(max(level, 1), 6)
            html_blocks.append(f"<h{level_num}>{parse_inline_markdown(header_text)}</h{level_num}>")
            continue
            
        # Scene separator or horizontal rule
        if stripped in ("*", "* * *", "***", "---", "___", "#"):
            flush_para()
            html_blocks.append('<p class="separator">* * *</p>')
            continue
            
        # List items
        if stripped.startswith("* ") or stripped.startswith("- "):
            flush_para()
            list_text = stripped[2:].strip()
            if not in_list:
                html_blocks.append("<ul>")
                in_list = True
            html_blocks.append(f"  <li>{parse_inline_markdown(list_text)}</li>")
            continue
            
        # Blockquote items
        if stripped.startswith(">"):
            flush_para()
            quote_text = stripped[1:].strip()
            if not in_blockquote:
                html_blocks.append("<blockquote>")
                in_blockquote = True
            html_blocks.append(f"  <p>{parse_inline_markdown(quote_text)}</p>")
            continue
            
        # Standard paragraph line accumulator
        current_para.append(line)
        
    flush_para()
    if in_list:
        html_blocks.append("</ul>")
    if in_blockquote:
        html_blocks.append("</blockquote>")
        
    return "\n".join(html_blocks)


def extract_book_metadata(db: BookDb, default_title: str) -> tuple:
    """Attempts to find the book author, title, and cover image path/UUID from metadata in the binder."""
    title = default_title
    author = "Unknown Author"
    cover = None
    
    # Simple search in the outline list for Prompt Directives
    pd_node = None
    try:
        outline = db.get_outline()
        # Search depth-1 and depth-2 nodes
        for node in outline:
            if node.title.lower() == "prompt directives":
                pd_node = node
                break
            for child in node.children:
                if child.title.lower() == "prompt directives":
                    pd_node = child
                    break
    except Exception:
        pass
            
    if pd_node:
        try:
            sf = db.read_scene(pd_node.uuid)
            notes_text = sf.notes
            if notes_text:
                sections = parse_section_tables(notes_text)
                metadata_rows = sections.get("agent metadata") or sections.get("metadata") or sections.get("default")
                if metadata_rows:
                    meta_dict = extract_metadata_from_table(metadata_rows)
                    if "author" in meta_dict and meta_dict["author"]:
                        author = meta_dict["author"]
                    if "title" in meta_dict and meta_dict["title"]:
                        title = meta_dict["title"]
                    if "cover" in meta_dict and meta_dict["cover"]:
                        cover = meta_dict["cover"]
        except Exception:
            pass
            
    return title, author, cover


def find_image_node(outline: list[BinderNode], value: str) -> Optional[BinderNode]:
    """Recursively searches outline nodes for an image node matching the value (UUID, title, or filename)."""
    if not value:
        return None
    val_clean = value.strip().lower()
    
    # 1. First pass: try matching by exact UUID or title (ignoring case)
    for node in outline:
        if node.type == "Image":
            if node.uuid.lower() == val_clean or node.title.lower() == val_clean:
                return node
            # Also check if title minus extension matches (e.g. "A_KDP_cover" matches "A_KDP_cover.jpg")
            title_base = os.path.splitext(node.title)[0].lower()
            if title_base == val_clean:
                return node
        
        # Recurse children
        res = find_image_node(node.children, value)
        if res:
            return res
            
    # 2. Second pass: check if value is a path (e.g. "Notes/Artwork/A_KDP_cover.jpg")
    if "/" in value or "\\" in value:
        last_part = re.split(r'[/\\]', value)[-1].strip().lower()
        for node in outline:
            if node.type == "Image":
                if node.title.lower() == last_part or os.path.splitext(node.title)[0].lower() == last_part:
                    return node
            res = find_image_node(node.children, last_part)
            if res:
                return res
                
    return None


def find_first_image_parent_uuid(outline: list[BinderNode], parent_uuid: str = None) -> Optional[str]:
    """Recursively traverses the outline to find the parent UUID of the first Image node."""
    for node in outline:
        if node.type == "Image":
            return parent_uuid
        res = find_first_image_parent_uuid(node.children, node.uuid)
        if res:
            return res
    return None


def find_folder_by_name(outline: list[BinderNode], name: str) -> Optional[str]:
    """Recursively searches outline nodes for a folder matching name (case-insensitive)."""
    for node in outline:
        if node.type in ("Folder", "ResearchFolder", "DraftFolder") and node.title.lower() == name.lower():
            return node.uuid
        res = find_folder_by_name(node.children, name)
        if res:
            return res
    return None


def update_metadata_table_in_notes(notes_text: str, attribute: str, new_value: str) -> str:
    """Updates or inserts an attribute-value row in the Markdown table under the metadata heading in notes."""
    if not notes_text:
        return f"### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| {attribute} | {new_value} |\n"
        
    lines = notes_text.split("\n")
    
    # 1. Find the metadata section
    meta_section_idx = -1
    for idx, line in enumerate(lines):
        line_clean = line.strip().lower()
        if line_clean.startswith("#") and ("metadata" in line_clean):
            meta_section_idx = idx
            break
            
    if meta_section_idx == -1:
        return notes_text.rstrip() + f"\n\n### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| {attribute} | {new_value} |\n"
        
    # 2. Find the table start within or after that section
    table_start_idx = -1
    for idx in range(meta_section_idx + 1, len(lines)):
        if lines[idx].strip().startswith("#"):
            break
        if lines[idx].strip().startswith("|"):
            table_start_idx = idx
            break
            
    if table_start_idx == -1:
        lines.insert(meta_section_idx + 1, "| Attribute | Value |")
        lines.insert(meta_section_idx + 2, "| --- | --- |")
        lines.insert(meta_section_idx + 3, f"| {attribute} | {new_value} |")
        return "\n".join(lines)
        
    # 3. We found a table. Look for existing row with the attribute
    attr_lower = attribute.lower().strip()
    row_idx = -1
    j = table_start_idx + 2  # Skip headers and separator line
    while j < len(lines) and lines[j].strip().startswith("|"):
        row = lines[j]
        parts = [p.strip() for p in row.split("|")[1:-1]]
        if parts and parts[0].lower().strip() == attr_lower:
            row_idx = j
            break
        j += 1
        
    if row_idx != -1:
        parts = [p.strip() for p in lines[row_idx].split("|")[1:-1]]
        if len(parts) >= 2:
            parts[1] = new_value
            lines[row_idx] = f"| {' | '.join(parts)} |"
        else:
            lines[row_idx] = f"| {attribute} | {new_value} |"
    else:
        lines.insert(j, f"| {attribute} | {new_value} |")
        
    return "\n".join(lines)



def generate_epub_components(db: BookDb) -> tuple:
    """Recursively walks the Manuscript outline in compile order and generates flat pages
    along with hierarchical HTML and NCX Table of Contents blocks.
    """
    try:
        outline = db.get_outline()
    except Exception as e:
        raise ValueError(f"Could not retrieve project outline: {e}")
        
    ms_node = next((n for n in outline if n.type == TYPE_DRAFT_FOLDER), None)
    if not ms_node:
        raise ValueError("Manuscript folder not found in outline.")
        
    pages = []
    play_order = 2  # Cover is 1
    
    def traverse(node: BinderNode, depth: int = 1):
        nonlocal play_order
        if not node.include_in_compile:
            return None, None
            
        page_dict = None
        has_content = False
        html_body = ""
        
        if node.type == TYPE_FOLDER:
            has_content = True
            html_body = f"<h1>{html.escape(node.title)}</h1>"
        elif node.type == TYPE_TEXT:
            try:
                sf = db.read_scene(node.uuid)
                text_content = sf.text.strip()
            except Exception:
                text_content = ""
            if text_content:
                has_content = True
                html_body = f"<h2>{html.escape(node.title)}</h2>\n{markdown_to_xhtml(text_content)}"
                
        if has_content:
            page_idx = len(pages) + 1
            filename = f"page_{page_idx}.xhtml"
            item_id = f"page_{page_idx}"
            
            page_dict = {
                "filename": filename,
                "item_id": item_id,
                "title": node.title,
                "depth": depth,
                "html_body": html_body
            }
            pages.append(page_dict)
            
            current_play_order = play_order
            play_order += 1
            
            html_toc = f'<li><a href="{filename}">{html.escape(node.title)}</a>'
            ncx_toc = f'<navPoint id="navpoint-{item_id}" playOrder="{current_play_order}">\n  <navLabel><text>{html.escape(node.title)}</text></navLabel>\n  <content src="{filename}"/>'
        else:
            html_toc = ""
            ncx_toc = ""
            
        child_htmls = []
        child_ncxs = []
        for child in node.children:
            ch_html, ch_ncx = traverse(child, depth + 1)
            if ch_html:
                child_htmls.append(ch_html)
            if ch_ncx:
                child_ncxs.append(ch_ncx)
                
        if page_dict:
            if child_htmls:
                html_toc += "\n  <ol>\n"
                for ch in child_htmls:
                    indented = "\n".join("    " + l for l in ch.split("\n"))
                    html_toc += indented + "\n"
                html_toc += "  </ol>\n</li>"
            else:
                html_toc += "</li>"
                
            if child_ncxs:
                ncx_toc += "\n"
                for ch in child_ncxs:
                    indented = "\n".join("  " + l for l in ch.split("\n"))
                    ncx_toc += indented + "\n"
            ncx_toc += "</navPoint>"
            
            return html_toc, ncx_toc
        else:
            joined_html = "\n".join(child_htmls)
            joined_ncx = "\n".join(child_ncxs)
            return joined_html, joined_ncx

    html_list = []
    ncx_list = []
    for child in ms_node.children:
        ch_html, ch_ncx = traverse(child, depth=1)
        if ch_html:
            html_list.append(ch_html)
        if ch_ncx:
            ncx_list.append(ch_ncx)
            
    return pages, "\n".join(html_list), "\n".join(ncx_list)


def build_epub(db: BookDb, output_path: str):
    """Assembles a Kindle-compatible EPUB3 container from the BookDb project drafts."""
    # 1. Resolve Title and Author metadata
    proj_dir_name = os.path.basename(db.project_path.rstrip("/"))
    if proj_dir_name.endswith(".gitbook"):
        fallback_title = proj_dir_name[:-8]
    elif proj_dir_name.endswith(".scriv"):
        fallback_title = proj_dir_name[:-6]
    else:
        fallback_title = proj_dir_name
    fallback_title = fallback_title.replace("_", " ")
    
    book_title, book_author, book_cover = extract_book_metadata(db, fallback_title)
    
    cover_image_added = False
    cover_filename = None
    cover_mime = None
    cover_bytes = None
    
    if book_cover:
        try:
            outline = db.get_outline()
            cover_node = find_image_node(outline, book_cover)
            
            def save_new_cover_metadata(new_val: str):
                pd_node = None
                for node in outline:
                    if node.title.lower() == "prompt directives":
                        pd_node = node
                        break
                    for child in node.children:
                        if child.title.lower() == "prompt directives":
                            pd_node = child
                            break
                if pd_node:
                    sf = db.read_scene(pd_node.uuid)
                    updated_notes = update_metadata_table_in_notes(sf.notes, "Cover", new_val)
                    db.write_scene(pd_node.uuid, notes=updated_notes)
            
            if cover_node:
                img_bytes, mime_type = db.read_image_bytes(cover_node.uuid)
                
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=os.path.splitext(cover_node.title)[1], delete=False) as tmp_f:
                    tmp_f.write(img_bytes)
                    tmp_path = tmp_f.name
                
                try:
                    compliant = is_kdp_compliant(tmp_path)
                except Exception:
                    compliant = False
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                
                if compliant:
                    cover_bytes = img_bytes
                    cover_mime = mime_type
                    cover_filename = cover_node.title
                    if not cover_filename.lower().endswith((".jpg", ".jpeg")):
                        cover_filename = os.path.splitext(cover_filename)[0] + ".jpg"
                else:
                    base_name = os.path.splitext(cover_node.title)[0]
                    if not base_name.endswith("_kdp_cover"):
                        base_name += "_kdp_cover"
                    new_uuid = db.generate_kdp_cover(cover_node.uuid, base_name)
                    
                    cover_bytes, cover_mime = db.read_image_bytes(new_uuid)
                    cover_filename = base_name + ".jpg"
                    
                    save_new_cover_metadata(new_uuid)
            else:
                if os.path.exists(book_cover) and os.path.isfile(book_cover):
                    target_folder_uuid = find_first_image_parent_uuid(outline)
                    if not target_folder_uuid:
                        target_folder_uuid = find_folder_by_name(outline, "Notes")
                    if not target_folder_uuid:
                        target_folder_uuid = outline[0].uuid if outline else ""
                    
                    if target_folder_uuid:
                        base_name = os.path.basename(book_cover)
                        new_uuid = db.copy_image_into_project(book_cover, target_folder_uuid, base_name)
                        
                        kdp_name = os.path.splitext(base_name)[0]
                        if not kdp_name.endswith("_kdp_cover"):
                            kdp_name += "_kdp_cover"
                        kdp_uuid = db.generate_kdp_cover(new_uuid, kdp_name)
                        
                        cover_bytes, cover_mime = db.read_image_bytes(kdp_uuid)
                        cover_filename = kdp_name + ".jpg"
                        
                        save_new_cover_metadata(kdp_uuid)
                else:
                    print(f"Warning: Cover image '{book_cover}' not found in project or on disk.")
        except NotImplementedError:
            print("Warning: Cover image auto-formatting is not supported for this project engine type.")
            if 'cover_node' in locals() and cover_node:
                try:
                    cover_bytes, cover_mime = db.read_image_bytes(cover_node.uuid)
                    cover_filename = cover_node.title
                except Exception:
                    pass
        except Exception as e:
            print(f"Warning: Failed to process cover image '{book_cover}': {e}")

    # 2. Collect compile-eligible pages and compile nested TOC structures
    pages, html_toc_content, ncx_toc_content = generate_epub_components(db)
    if not pages:
        raise ValueError("No compile-eligible scenes with text content found in the Manuscript.")
        
    processed_pages = pages
    max_depth = max(p["depth"] for p in processed_pages) if processed_pages else 1
    
    book_uuid = str(uuid.uuid4())
    mod_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 3. Create the ZIP archive
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    with zipfile.ZipFile(output_path, "w") as epub:
        # The mimetype file must be the first file and uncompressed
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        
        # All other files can be compressed
        compress = zipfile.ZIP_DEFLATED
        
        # META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        epub.writestr("META-INF/container.xml", container_xml, compress_type=compress)
        
        if cover_bytes and cover_filename:
            epub.writestr(f"OEBPS/{cover_filename}", cover_bytes, compress_type=compress)
            cover_image_added = True

        
        # OEBPS/stylesheet.css
        stylesheet_css = """body {
  font-family: Georgia, serif;
  margin: 5%;
  line-height: 1.5;
  color: #111111;
  background-color: #ffffff;
}

h1.booktitle {
  text-align: center;
  margin-top: 3em;
  margin-bottom: 0.5em;
  font-size: 2.2em;
  font-weight: bold;
}

h2.bookauthor {
  text-align: center;
  margin-bottom: 5em;
  font-size: 1.4em;
  font-style: italic;
  font-weight: normal;
}

h1, h2, h3, h4, h5, h6 {
  text-align: center;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
  font-weight: bold;
  page-break-after: avoid;
}

p {
  text-indent: 1.5em;
  margin: 0 0 0.5em 0;
  text-align: justify;
}

p:first-of-type, h1 + p, h2 + p, h3 + p, h4 + p, .titlepage + p {
  text-indent: 0;
}

p.separator {
  text-align: center;
  text-indent: 0;
  margin: 1.5em 0;
  font-size: 1.2em;
}

ul, ol {
  margin: 1em 0;
  padding-left: 2em;
}

li {
  margin-bottom: 0.5em;
}

blockquote {
  margin: 1em 2em;
  font-style: italic;
  color: #555555;
  border-left: 4px solid #cccccc;
  padding-left: 1em;
}

pre {
  background-color: #f5f5f5;
  padding: 1em;
  border-radius: 4px;
  overflow-x: auto;
}

code {
  font-family: Courier, monospace;
  font-size: 0.95em;
}
"""
        epub.writestr("OEBPS/stylesheet.css", stylesheet_css, compress_type=compress)
        
        # OEBPS/cover.xhtml (Title Page)
        cover_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head>
    <title>{html.escape(book_title)}</title>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="stylesheet.css" type="text/css"/>
  </head>
  <body>
    <section class="titlepage" epub:type="titlepage">
      <h1 class="booktitle">{html.escape(book_title)}</h1>
      <h2 class="bookauthor">By {html.escape(book_author)}</h2>
    </section>
  </body>
</html>"""
        epub.writestr("OEBPS/cover.xhtml", cover_xhtml, compress_type=compress)
        
        # OEBPS/nav.xhtml (HTML Navigation TOC)
        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head>
    <title>Table of Contents</title>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="stylesheet.css" type="text/css"/>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
        <li><a href="cover.xhtml">Title Page</a></li>
{html_toc_content}
      </ol>
    </nav>
    <nav epub:type="landmarks" id="landmarks" hidden="hidden">
      <h2>Guide</h2>
      <ol>
        <li><a epub:type="cover" href="cover.xhtml">Cover</a></li>
        <li><a epub:type="toc" href="nav.xhtml">Table of Contents</a></li>
        <li><a epub:type="bodymatter" href="page_1.xhtml">Start Reading</a></li>
      </ol>
    </nav>
  </body>
</html>"""
        epub.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=compress)
        
        # OEBPS/toc.ncx (EPUB2 TOC Compatibility)
        toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_uuid}"/>
    <meta name="dtb:depth" content="{max_depth}"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(book_title)}</text></docTitle>
  <navMap>
    <navPoint id="navpoint-cover" playOrder="1">
      <navLabel><text>Title Page</text></navLabel>
      <content src="cover.xhtml"/>
    </navPoint>
{ncx_toc_content}
  </navMap>
</ncx>"""
        epub.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=compress)
        
        # Write individual chapter XHTML pages
        for p in processed_pages:
            chap_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head>
    <title>{html.escape(p["title"])}</title>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="stylesheet.css" type="text/css"/>
  </head>
  <body>
    <section epub:type="chapter">
      {p["html_body"]}
    </section>
  </body>
</html>"""
            epub.writestr(f"OEBPS/{p['filename']}", chap_xhtml, compress_type=compress)
            
        # OEBPS/content.opf (Manifest and Spine XML)
        manifest_entries = []
        manifest_entries.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        manifest_entries.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        manifest_entries.append('<item id="css" href="stylesheet.css" media-type="text/css"/>')
        manifest_entries.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        
        meta_cover = ""
        if cover_image_added:
            manifest_entries.append(f'<item id="cover-image" href="{cover_filename}" media-type="{cover_mime}" properties="cover-image"/>')
            meta_cover = '\n    <meta name="cover" content="cover-image"/>'
            
        for p in processed_pages:
            manifest_entries.append(f'<item id="{p["item_id"]}" href="{p["filename"]}" media-type="application/xhtml+xml"/>')
            
        spine_entries = []
        spine_entries.append('<itemref idref="cover"/>')
        spine_entries.append('<itemref idref="nav"/>')
        for p in processed_pages:
            spine_entries.append(f'<itemref idref="{p["item_id"]}"/>')
            
        content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="pub-id" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{book_uuid}</dc:identifier>
    <dc:title>{html.escape(book_title)}</dc:title>
    <dc:creator id="creator">{html.escape(book_author)}</dc:creator>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">{mod_time}</meta>{meta_cover}
  </metadata>
  <manifest>
    {chr(10).join(manifest_entries)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join(spine_entries)}
  </spine>
  <guide>
    <reference type="cover" title="Cover" href="cover.xhtml"/>
    <reference type="toc" title="Table of Contents" href="nav.xhtml"/>
    <reference type="text" title="Start Reading" href="page_1.xhtml"/>
  </guide>
</package>"""
        epub.writestr("OEBPS/content.opf", content_opf, compress_type=compress)


def slugify(text: str) -> str:
    """Generates standard, lowercase, punctuation-free GitHub-style anchors."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def extract_first_heading(text: str) -> Optional[str]:
    """Scans the scene text for the first Markdown heading."""
    for line in text.split('\n'):
        line_stripped = line.strip()
        m = re.match(r'^(#+)\s+(.+)$', line_stripped)
        if m:
            return m.group(2).strip()
    return None


def build_markdown(db: BookDb, output_path: str):
    """Compiles all compile-eligible scenes from BookDb into a single Markdown file with a Table of Contents."""
    proj_dir_name = os.path.basename(db.project_path.rstrip("/"))
    if proj_dir_name.endswith(".gitbook"):
        fallback_title = proj_dir_name[:-8]
    elif proj_dir_name.endswith(".scriv"):
        fallback_title = proj_dir_name[:-6]
    else:
        fallback_title = proj_dir_name
    fallback_title = fallback_title.replace("_", " ")
    
    book_title, book_author, _ = extract_book_metadata(db, fallback_title)
    
    try:
        outline = db.get_outline()
    except Exception as e:
        raise ValueError(f"Could not retrieve project outline: {e}")
        
    ms_node = next((n for n in outline if n.type == TYPE_DRAFT_FOLDER), None)
    if not ms_node:
        raise ValueError("Manuscript folder not found in outline.")
        
    chapters = []
    seen_slugs = set()
    
    def get_unique_slug(title: str) -> str:
        base_slug = slugify(title)
        if not base_slug:
            base_slug = "chapter"
        slug = base_slug
        counter = 1
        while slug in seen_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        seen_slugs.add(slug)
        return slug

    def traverse(node: BinderNode, depth: int = 1):
        if not node.include_in_compile:
            return None
            
        chapter_dict = None
        has_content = False
        text_content = ""
        title = node.title
        has_heading = False
        
        if node.type == TYPE_FOLDER:
            has_content = True
        elif node.type == TYPE_TEXT:
            try:
                sf = db.read_scene(node.uuid)
                text_content = sf.text.strip()
            except Exception:
                text_content = ""
            if text_content:
                has_content = True
                extracted_title = extract_first_heading(text_content)
                if extracted_title:
                    title = extracted_title
                    has_heading = True
                    
        if has_content:
            slug = get_unique_slug(title)
            if has_heading:
                content = text_content
            else:
                heading_prefix = '#' * depth
                if text_content:
                    content = f"{heading_prefix} {title}\n\n{text_content}"
                else:
                    content = f"{heading_prefix} {title}"
                    
            chapter_dict = {
                "title": title,
                "depth": depth,
                "slug": slug,
                "content": content
            }
            chapters.append(chapter_dict)
            
            indent = "  " * (depth - 1)
            toc_line = f"{indent}- [{title}](#{slug})"
        else:
            toc_line = ""
            
        child_tocs = []
        for child in node.children:
            ch_toc = traverse(child, depth + 1)
            if ch_toc:
                child_tocs.append(ch_toc)
                
        if chapter_dict:
            if child_tocs:
                toc_line += "\n" + "\n".join(child_tocs)
            return toc_line
        else:
            return "\n".join(child_tocs)

    toc_lines = []
    for child in ms_node.children:
        ch_toc = traverse(child, depth=1)
        if ch_toc:
            toc_lines.append(ch_toc)
            
    if not chapters:
        raise ValueError("No compile-eligible scenes with text content found in the Manuscript.")
        
    toc_str = "\n".join(toc_lines)
    
    output_lines = []
    output_lines.append(f"# {book_title}")
    output_lines.append(f"**By {book_author}**")
    output_lines.append("")
    output_lines.append("# Table of Contents")
    output_lines.append("")
    output_lines.append(toc_str)
    output_lines.append("")
    output_lines.append("\n\n".join(ch["content"] for ch in chapters))
    output_lines.append("")
    
    final_content = "\n".join(output_lines)
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_content)


def extract_print_metadata(db: BookDb) -> dict:
    """Attempts to find the print settings in metadata in the binder."""
    settings = {
        "trim_width": 6.0,
        "trim_height": 9.0,
        "bleed": False,
        "gutter": None,
        "outside_margin": 0.375,
        "top_margin": 0.375,
        "bottom_margin": 0.375,
    }
    
    pd_node = None
    try:
        outline = db.get_outline()
        for node in outline:
            if node.title.lower() == "prompt directives":
                pd_node = node
                break
            for child in node.children:
                if child.title.lower() == "prompt directives":
                    pd_node = child
                    break
    except Exception:
        pass
        
    if pd_node:
        try:
            sf = db.read_scene(pd_node.uuid)
            notes_text = sf.notes
            if notes_text:
                sections = parse_section_tables(notes_text)
                rows = (sections.get("print settings") or 
                        sections.get("agent metadata") or 
                        sections.get("metadata") or 
                        sections.get("default"))
                if rows:
                    meta_dict = extract_metadata_from_table(rows)
                    
                    def to_float(val, default):
                        if not val:
                            return default
                        try:
                            cleaned = re.sub(r'[^\d\.]', '', val)
                            return float(cleaned)
                        except ValueError:
                            return default
                            
                    def to_bool(val, default):
                        if not val:
                            return default
                        return val.strip().lower() in ("true", "yes", "1", "y")
                        
                    for k, v in meta_dict.items():
                        k_clean = k.lower().replace(" ", "_")
                        if "trim_width" in k_clean or k_clean == "width":
                            settings["trim_width"] = to_float(v, settings["trim_width"])
                        elif "trim_height" in k_clean or k_clean == "height":
                            settings["trim_height"] = to_float(v, settings["trim_height"])
                        elif "bleed" in k_clean:
                            settings["bleed"] = to_bool(v, settings["bleed"])
                        elif "gutter" in k_clean or "inside_margin" in k_clean:
                            if v.strip().lower() == "auto":
                                settings["gutter"] = "auto"
                            else:
                                settings["gutter"] = to_float(v, settings["gutter"])
                        elif "outside_margin" in k_clean or "side_margin" in k_clean:
                            settings["outside_margin"] = to_float(v, settings["outside_margin"])
                        elif "top_margin" in k_clean:
                            settings["top_margin"] = to_float(v, settings["top_margin"])
                        elif "bottom_margin" in k_clean:
                            settings["bottom_margin"] = to_float(v, settings["bottom_margin"])
        except Exception:
            pass
            
    return settings


def update_print_metadata(db: BookDb, settings: dict):
    """Saves or updates print settings in the Prompt Directives notes metadata table."""
    pd_node = None
    try:
        outline = db.get_outline()
        for node in outline:
            if node.title.lower() == "prompt directives":
                pd_node = node
                break
            for child in node.children:
                if child.title.lower() == "prompt directives":
                    pd_node = child
                    break
    except Exception:
        pass
        
    if pd_node:
        try:
            sf = db.read_scene(pd_node.uuid)
            notes = sf.notes or ""
            
            # Map settings to clean display names
            mapping = {
                "Trim Width": f"{settings['trim_width']} in",
                "Trim Height": f"{settings['trim_height']} in",
                "Bleed": "Yes" if settings["bleed"] else "No",
                "Gutter": f"{settings['gutter']} in" if settings.get("gutter") is not None and settings["gutter"] != "auto" else "Auto",
                "Outside Margin": f"{settings['outside_margin']} in",
                "Top Margin": f"{settings['top_margin']} in",
                "Bottom Margin": f"{settings['bottom_margin']} in"
            }
            for attribute, val in mapping.items():
                notes = update_metadata_table_in_notes(notes, attribute, val)
                
            db.write_scene(pd_node.uuid, notes=notes)
        except Exception as e:
            print(f"Warning: Failed to update print metadata: {e}")


def clean_inline_tags(text: str) -> str:
    """Converts common XHTML tags generated by our markdown parser into ReportLab-supported tags."""
    text = text.replace("<em>", "<i>").replace("</em>", "</i>")
    text = text.replace("<strong>", "<b>").replace("</strong>", "</b>")
    return text


def html_to_flowables(html_text: str, styles) -> list:
    """Parses standard XHTML blocks from markdown_to_xhtml into ReportLab Flowable blocks."""
    from reportlab.platypus import Paragraph
    flowables = []
    
    html_text = html_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = html_text.split("\n")
    in_list = False
    in_blockquote = False
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
            
        if stripped.startswith("<pre><code>"):
            content = stripped[len("<pre><code>"):]
            if content.endswith("</code></pre>"):
                content = content[:-len("</code></pre>")]
            content = html.unescape(content)
            flowables.append(Paragraph(content, styles['PrintCode']))
            continue
            
        if stripped == "<ul>":
            in_list = True
            continue
        if stripped == "</ul>":
            in_list = False
            continue
            
        if stripped == "<blockquote>":
            in_blockquote = True
            continue
        if stripped == "</blockquote>":
            in_blockquote = False
            continue
            
        if stripped.startswith("<li>") and stripped.endswith("</li>"):
            content = stripped[4:-5]
            content = clean_inline_tags(content)
            flowables.append(Paragraph(content, styles['PrintBullet']))
            continue
            
        if in_blockquote:
            if stripped.startswith("<p>") and stripped.endswith("</p>"):
                content = stripped[3:-4]
                content = clean_inline_tags(content)
                flowables.append(Paragraph(content, styles['PrintBlockquote']))
                continue
                
        m_heading = re.match(r'^<h([1-6])>(.*?)</h\1>$', stripped)
        if m_heading:
            level = int(m_heading.group(1))
            content = m_heading.group(2)
            content = clean_inline_tags(content)
            style_name = 'PrintChapterHeading' if level > 1 else 'PrintPartHeading'
            flowables.append(Paragraph(content, styles[style_name]))
            continue
            
        if stripped == '<p class="separator">* * *</p>':
            flowables.append(Paragraph("* * *", styles['PrintSeparator']))
            continue
            
        if stripped.startswith("<p>") and stripped.endswith("</p>"):
            content = stripped[3:-4]
            content = clean_inline_tags(content)
            
            # Typographic standard: no first-line indentation for paragraph directly following a heading
            if flowables and isinstance(flowables[-1], Paragraph) and flowables[-1].style.name in ('PrintChapterHeading', 'PrintPartHeading'):
                flowables.append(Paragraph(content, styles['PrintFirstBody']))
            else:
                flowables.append(Paragraph(content, styles['PrintBody']))
            continue
            
    return flowables




def register_embedded_fonts():
    """Registers TrueType fonts from the host OS to override the standard PDF 14 fonts,
    forcing ReportLab to embed font subsets inside the generated PDF file.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    font_paths = {
        'Times-Roman': '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
        'Times-Bold': '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf',
        'Times-Italic': '/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf',
        'Times-BoldItalic': '/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf',
        'Courier': '/System/Library/Fonts/Supplemental/Courier New.ttf',
        'Courier-Bold': '/System/Library/Fonts/Supplemental/Courier New Bold.ttf',
    }
    
    registered_any = False
    for font_name, path in font_paths.items():
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                registered_any = True
            except Exception as e:
                print(f"Warning: Failed to register font {font_name} from {path}: {e}")
                
    if registered_any:
        try:
            pdfmetrics.registerFontFamily(
                "Times-Roman",
                normal="Times-Roman",
                bold="Times-Bold",
                italic="Times-Italic",
                boldItalic="Times-BoldItalic"
            )
            if 'Courier' in font_paths and os.path.exists(font_paths['Courier']):
                pdfmetrics.registerFontFamily(
                    "Courier",
                    normal="Courier",
                    bold="Courier-Bold"
                )
        except Exception as e:
            print(f"Warning: Failed to register font family mappings: {e}")


def build_pdf(
    db: BookDb,
    output_path: str,
    trim_width: Optional[float] = None,
    trim_height: Optional[float] = None,
    bleed: Optional[bool] = None,
    gutter: Optional[float] = None,
    outside_margin: Optional[float] = None,
    top_margin: Optional[float] = None,
    bottom_margin: Optional[float] = None
):
    """Compiles the manuscript and renders a KDP paperback-compliant print PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
    )

    # Ensure system TrueType fonts are registered to force full embedding in the PDF
    register_embedded_fonts()

    # 1. Resolve metadata for fallback settings
    proj_dir_name = os.path.basename(db.project_path.rstrip("/"))
    if proj_dir_name.endswith(".gitbook"):
        fallback_title = proj_dir_name[:-8]
    elif proj_dir_name.endswith(".scriv"):
        fallback_title = proj_dir_name[:-6]
    else:
        fallback_title = proj_dir_name
    fallback_title = fallback_title.replace("_", " ")

    book_title, book_author, _ = extract_book_metadata(db, fallback_title)
    
    # Load default settings from metadata or fallbacks
    meta_settings = extract_print_metadata(db)
    
    # Merge passed parameters with metadata defaults
    w = trim_width if trim_width is not None else meta_settings["trim_width"]
    h = trim_height if trim_height is not None else meta_settings["trim_height"]
    is_bleed = bleed if bleed is not None else meta_settings["bleed"]
    g = gutter if gutter is not None else meta_settings["gutter"]
    o_margin = outside_margin if outside_margin is not None else meta_settings["outside_margin"]
    t_margin = top_margin if top_margin is not None else meta_settings["top_margin"]
    b_margin = bottom_margin if bottom_margin is not None else meta_settings["bottom_margin"]

    # 2. Compile manuscript content
    pages, _, _ = generate_epub_components(db)
    if not pages:
        raise ValueError("No compile-eligible scenes with text content found in the Manuscript.")

    # 3. Estimate page count for auto-gutter calculation
    total_words = 0
    for p in pages:
        text_only = re.sub(r'<[^>]+>', ' ', p["html_body"])
        total_words += len(text_only.split())
        
    estimated_pages = max(24, int(total_words / 250))
    
    if g is None or (isinstance(g, str) and str(g).lower() == "auto"):
        # Auto-calculate gutter based on KDP guidelines
        if estimated_pages <= 150:
            g = 0.375
        elif estimated_pages <= 300:
            g = 0.5
        elif estimated_pages <= 500:
            g = 0.625
        elif estimated_pages <= 700:
            g = 0.75
        else:
            g = 0.875
            
    # Save active settings back as project defaults
    active_settings = {
        "trim_width": w,
        "trim_height": h,
        "bleed": is_bleed,
        "gutter": g,
        "outside_margin": o_margin,
        "top_margin": t_margin,
        "bottom_margin": b_margin
    }
    update_print_metadata(db, active_settings)

    # 4. Compute layout dimensions (in points)
    pt_trim_w = w * 72.0
    pt_trim_h = h * 72.0
    
    if is_bleed:
        # With bleed, KDP requires page height to increase by 0.25" and page width by 0.125"
        pt_page_w = (w + 0.125) * 72.0
        pt_page_h = (h + 0.25) * 72.0
        # Gutter remains unchanged. Margins increase by bleed offset (0.125")
        pt_gutter = g * 72.0
        pt_outside = (o_margin + 0.125) * 72.0
        pt_top = (t_margin + 0.125) * 72.0
        pt_bottom = (b_margin + 0.125) * 72.0
    else:
        pt_page_w = pt_trim_w
        pt_page_h = pt_trim_h
        pt_gutter = g * 72.0
        pt_outside = o_margin * 72.0
        pt_top = t_margin * 72.0
        pt_bottom = b_margin * 72.0

    # 5. Define style sheet
    styles = getSampleStyleSheet()
    
    custom_styles = {
        'PrintBody': ParagraphStyle(
            name='PrintBody',
            fontName='Times-Roman',
            fontSize=11,
            leading=15.5,
            alignment=TA_JUSTIFY,
            firstLineIndent=18,
            spaceAfter=0,
            spaceBefore=0
        ),
        'PrintFirstBody': ParagraphStyle(
            name='PrintFirstBody',
            fontName='Times-Roman',
            fontSize=11,
            leading=15.5,
            alignment=TA_JUSTIFY,
            firstLineIndent=0,
            spaceAfter=0,
            spaceBefore=0
        ),
        'PrintChapterHeading': ParagraphStyle(
            name='PrintChapterHeading',
            fontName='Times-Bold',
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceBefore=40,
            spaceAfter=15,
            keepWithNext=True
        ),
        'PrintPartHeading': ParagraphStyle(
            name='PrintPartHeading',
            fontName='Times-Bold',
            fontSize=22,
            leading=26,
            alignment=TA_CENTER,
            spaceBefore=80,
            spaceAfter=20,
            keepWithNext=True
        ),
        'PrintSeparator': ParagraphStyle(
            name='PrintSeparator',
            fontName='Times-Roman',
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=12,
            spaceAfter=12
        ),
        'PrintBlockquote': ParagraphStyle(
            name='PrintBlockquote',
            fontName='Times-Italic',
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            leftIndent=20,
            rightIndent=20,
            spaceBefore=6,
            spaceAfter=6,
            firstLineIndent=0
        ),
        'PrintBullet': ParagraphStyle(
            name='PrintBullet',
            fontName='Times-Roman',
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            leftIndent=15,
            firstLineIndent=-10,
            spaceBefore=3,
            spaceAfter=3
        ),
        'PrintCode': ParagraphStyle(
            name='PrintCode',
            fontName='Courier',
            fontSize=9,
            leading=12,
            alignment=TA_LEFT,
            leftIndent=15,
            spaceBefore=4,
            spaceAfter=4
        )
    }
    
    for s_name, s_obj in custom_styles.items():
        if s_name in styles:
            styles[s_name].__dict__.update(s_obj.__dict__)
        else:
            styles.add(s_obj)

    # 6. Build Story Flowables
    story = []
    
    # Title Page
    story.append(Spacer(1, 150))
    story.append(Paragraph(book_title, styles['PrintPartHeading']))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"By {book_author}", styles['PrintBody']))
    story.append(PageBreak())
    
    # Traverse chapters
    for p in pages:
        html_body = p["html_body"]
        
        if html_body.strip().startswith("<h1>") and html_body.strip().endswith("</h1>"):
            title_text = re.sub(r'<[^>]+>', '', html_body).strip()
            story.append(Spacer(1, 100))
            story.append(Paragraph(title_text, styles['PrintPartHeading']))
            story.append(PageBreak())
        else:
            flowables = html_to_flowables(html_body, styles)
            if flowables:
                story.extend(flowables)
                story.append(PageBreak())
                
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    # 7. Create Mirrored Document Template with proper alternating templates
    class MirroredDocTemplate(BaseDocTemplate):
        def handle_pageBegin(self):
            # Sets template for page self.page + 2 (the next page to be rendered)
            next_template = "Even" if self.page % 2 == 0 else "Odd"
            self.handle_nextPageTemplate(next_template)
            super().handle_pageBegin()

    doc = MirroredDocTemplate(
        output_path,
        pagesize=(pt_page_w, pt_page_h)
    )

    # Odd page frame (Gutter on Left, Outside on Right)
    odd_frame = Frame(
        pt_gutter,
        pt_bottom,
        pt_page_w - pt_gutter - pt_outside,
        pt_page_h - pt_top - pt_bottom,
        id='odd_f',
        topPadding=0,
        bottomPadding=0,
        leftPadding=0,
        rightPadding=0
    )
    
    # Even page frame (Outside on Left, Gutter on Right)
    even_frame = Frame(
        pt_outside,
        pt_bottom,
        pt_page_w - pt_gutter - pt_outside,
        pt_page_h - pt_top - pt_bottom,
        id='even_f',
        topPadding=0,
        bottomPadding=0,
        leftPadding=0,
        rightPadding=0
    )

    odd_template = PageTemplate(id='Odd', frames=odd_frame)
    even_template = PageTemplate(id='Even', frames=even_frame)
    doc.addPageTemplates([odd_template, even_template])

    # 8. Setup NumberedMirroredCanvas for mirrored header/footers inside safe margins
    class NumberedMirroredCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_decorations(num_pages)
                super().showPage()
            super().save()

        def draw_page_decorations(self, total_pages):
            page_num = self._pageNumber
            if page_num == 1:
                return

            self.saveState()
            self.setFont("Times-Roman", 9)
            self.setFillColor(colors.HexColor("#333333"))

            is_odd = page_num % 2 == 1
            
            if is_odd:
                header_text = book_author
                center_x = pt_gutter + (pt_page_w - pt_gutter - pt_outside) / 2.0
            else:
                header_text = book_title
                center_x = pt_outside + (pt_page_w - pt_gutter - pt_outside) / 2.0

            # Safe Y coordinates inside the margins (KDP Safe Zone >= 0.25" for regular, >= 0.375" for bleed)
            # Center the header and footer inside the top/bottom margins, leaving a safe distance from both edge and body frame
            y_header = min(pt_page_h - pt_top + 18, pt_page_h - 32)
            y_line = y_header - 8
            y_footer = max(pt_bottom - 18, 32)

            # Draw running header text
            self.drawCentredString(center_x, y_header, header_text)

            # Draw thin divider line
            self.setStrokeColor(colors.HexColor("#cccccc"))
            self.setLineWidth(0.5)
            if is_odd:
                self.line(pt_gutter, y_line, pt_page_w - pt_outside, y_line)
            else:
                self.line(pt_outside, y_line, pt_page_w - pt_gutter, y_line)

            # Draw page number centered under body
            self.setFont("Times-Roman", 10)
            self.drawCentredString(center_x, y_footer, str(page_num))
            
            self.restoreState()

    doc.handle_nextPageTemplate('Odd')
    doc.build(story, canvasmaker=NumberedMirroredCanvas)

