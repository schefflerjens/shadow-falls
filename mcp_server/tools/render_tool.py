import os

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server
from mcp_server.renderer import build_epub, build_markdown, build_pdf


@server.register_tool(name='render', description='Renders the book project into a published format (such as Kindle-compatible ePub, print-ready PDF, or a single Markdown file).', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the book project directory (.scriv or .gitbook)'}, 'output_path': {'type': 'string', 'description': 'Absolute path (including filename) where the rendered ebook should be saved (e.g. /path/to/book.epub, /path/to/book.pdf, or /path/to/book.md)'}, 'format': {'type': 'string', 'description': "The publishing format. Supported formats: 'amazon' (epub), 'markdown', 'pdf' (KDP print PDF)", 'default': 'amazon'}, 'trim_width': {'type': 'number', 'description': 'Trim size width in inches (e.g., 6.0)'}, 'trim_height': {'type': 'number', 'description': 'Trim size height in inches (e.g., 9.0)'}, 'bleed': {'type': 'boolean', 'description': 'Set to true if images bleed to the edge of the printed pages'}, 'gutter': {'type': 'number', 'description': 'Gutter/inside margin in inches. Leave blank/auto for automatic KDP gutter margin calculation based on page count.'}, 'outside_margin': {'type': 'number', 'description': 'Outside side margin in inches (minimum 0.25 for no bleed, 0.375 for bleed)'}, 'top_margin': {'type': 'number', 'description': 'Top margin in inches'}, 'bottom_margin': {'type': 'number', 'description': 'Bottom margin in inches'}}, 'required': ['project_path', 'output_path']})
def render_tool(project_path: str, output_path: str, format: str='amazon', trim_width: Optional[float]=None, trim_height: Optional[float]=None, bleed: Optional[bool]=None, gutter: Optional[float]=None, outside_margin: Optional[float]=None, top_margin: Optional[float]=None, bottom_margin: Optional[float]=None) -> dict:
    try:
        format_lower = format.lower()
        if format_lower not in ('amazon', 'markdown', 'pdf'):
            return {'content': [{'type': 'text', 'text': f"Unsupported format '{format}'. Supported formats: 'amazon', 'markdown', 'pdf'."}], 'isError': True}
        expanded_proj = os.path.expanduser(project_path)
        expanded_out = os.path.expanduser(output_path)
        db = get_book_db(expanded_proj)
        if format_lower == 'amazon':
            build_epub(db, expanded_out)
        elif format_lower == 'pdf':
            build_pdf(db, expanded_out, trim_width=trim_width, trim_height=trim_height, bleed=bleed, gutter=gutter, outside_margin=outside_margin, top_margin=top_margin, bottom_margin=bottom_margin)
        else:
            build_markdown(db, expanded_out)
        return {'content': [{'type': 'text', 'text': f"Successfully rendered book in '{format_lower}' format to: {expanded_out}"}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error rendering book: {str(e)}'}], 'isError': True}
