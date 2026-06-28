import json
import os
import re
import ssl
import sys
import urllib.request

from mcp_server.book_codex import (
    extract_metadata_from_table,
    parse_section_tables,
)
from mcp_server.engine.book_engine import get_book_db

GENRE_PRESETS = {
    'middle grade': {
        'genre': 'Middle Grade',
        'grade_level_min': 4.5,
        'grade_level_max': 6.5,
        'avg_sentence_length_min': 10.0,
        'avg_sentence_length_max': 14.0,
        'max_adverb_density': 1.0,
        'max_passive_density': 4.0,
        'max_filler_density': 1.2
    },
    'young adult': {
        'genre': 'Young Adult',
        'grade_level_min': 6.0,
        'grade_level_max': 8.0,
        'avg_sentence_length_min': 12.0,
        'avg_sentence_length_max': 16.0,
        'max_adverb_density': 1.3,
        'max_passive_density': 6.0,
        'max_filler_density': 1.5
    },
    'general fiction': {
        'genre': 'General Adult Fiction',
        'grade_level_min': 7.0,
        'grade_level_max': 10.0,
        'avg_sentence_length_min': 14.0,
        'avg_sentence_length_max': 18.0,
        'max_adverb_density': 1.6,
        'max_passive_density': 8.0,
        'max_filler_density': 1.8
    }
}



def load_env_file(project_path: str=None):
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'load_env_file'):
        func = server_mod.load_env_file
        if func is not load_env_file:
            return func(project_path)
    return _impl_load_env_file(project_path)

def _impl_load_env_file(project_path: str=None):
    """Loads environment variables from a .env file if present in standard locations."""
    dirs_to_check = []
    if project_path:
        dirs_to_check.append(os.path.dirname(os.path.abspath(os.path.expanduser(project_path))))
    dirs_to_check.append(os.getcwd())
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs_to_check.append(repo_root)
    for directory in dirs_to_check:
        env_path = os.path.join(directory, '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip()
                            if v.startswith(('"', "'")) and v.endswith(v[0]):
                                v = v[1:-1]
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception as e:
                sys.stderr.write(f'Warning: Failed to parse .env file at {env_path}: {e}\n')
                sys.stderr.flush()

def find_notes_editor_node(db: BookDb) -> Optional[BinderNode]:
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'find_notes_editor_node'):
        func = server_mod.find_notes_editor_node
        if func is not find_notes_editor_node:
            return func(db)
    return _impl_find_notes_editor_node(db)

def _impl_find_notes_editor_node(db: BookDb) -> Optional[BinderNode]:
    """Finds the 'Editor' folder node under the 'Notes' folder node in the binder outline."""
    outline = db.get_outline()
    notes_node = next((n for n in outline if n.title == 'Notes'), None)
    if not notes_node:

        def find_notes_folder(nodes):
            for n in nodes:
                if n.title == 'Notes':
                    return n
                res = find_notes_folder(n.children)
                if res:
                    return res
            return None
        notes_node = find_notes_folder(outline)
    if not notes_node:
        return None
    return next((c for c in notes_node.children if c.title == 'Editor'), None)

def read_editor_artifact(project_path: str, filename: str) -> Optional[str]:
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'read_editor_artifact'):
        func = server_mod.read_editor_artifact
        if func is not read_editor_artifact:
            return func(project_path, filename)
    return _impl_read_editor_artifact(project_path, filename)

def _impl_read_editor_artifact(project_path: str, filename: str) -> Optional[str]:
    """Attempts to read an editor artifact from the project binder under 'Notes/Editor'."""
    try:
        db = get_book_db(project_path)
        editor_node = find_notes_editor_node(db)
        if editor_node:
            file_node = next((c for c in editor_node.children if c.title == filename), None)
            if file_node:
                scene_files = db.read_scene(file_node.uuid)
                return scene_files.text
    except Exception:
        pass
    return None

def write_editor_artifact(project_path: str, filename: str, content: str):
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'write_editor_artifact'):
        func = server_mod.write_editor_artifact
        if func is not write_editor_artifact:
            return func(project_path, filename, content)
    return _impl_write_editor_artifact(project_path, filename, content)

def _impl_write_editor_artifact(project_path: str, filename: str, content: str):
    """Saves/updates an editorial artifact file inside 'Notes/Editor' folder of the project binder."""
    db = get_book_db(project_path)
    outline = db.get_outline()
    notes_node = next((n for n in outline if n.title == 'Notes'), None)
    if not notes_node:

        def find_notes_folder(nodes):
            for n in nodes:
                if n.title == 'Notes':
                    return n
                res = find_notes_folder(n.children)
                if res:
                    return res
            return None
        notes_node = find_notes_folder(outline)
    if not notes_node:
        raise ValueError("Could not find top-level 'Notes' folder in the project outline.")
    editor_node = next((c for c in notes_node.children if c.title == 'Editor'), None)
    if not editor_node:
        editor_uuid = db.create_binder_item(parent_uuid=notes_node.uuid, title='Editor', item_type='Folder')
        outline = db.get_outline()

        def find_uuid(nodes, u):
            for n in nodes:
                if n.uuid == u:
                    return n
                res = find_uuid(n.children, u)
                if res:
                    return res
            return None
        editor_node = find_uuid(outline, editor_uuid)
    if not editor_node:
        raise ValueError("Failed to create or retrieve the 'Editor' folder.")
    file_node = next((c for c in editor_node.children if c.title == filename), None)
    if not file_node:
        file_uuid = db.create_binder_item(parent_uuid=editor_node.uuid, title=filename, item_type='Text')
    else:
        file_uuid = file_node.uuid
    db.write_scene(uuid=file_uuid, text=content)
    return file_uuid

def get_project_model_setting(project_path: str, task_type: str=None) -> str:
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'get_project_model_setting'):
        func = server_mod.get_project_model_setting
        if func is not get_project_model_setting:
            return func(project_path, task_type)
    return _impl_get_project_model_setting(project_path, task_type)

def _impl_get_project_model_setting(project_path: str, task_type: str=None) -> str:
    """Finds Prompt Directives document notes and parses the model configuration from ### Agent Metadata.
    Supports task-specific models (e.g. 'Drafting Model', 'Critique Model', 'Model').
    Raises ValueError if not configured, instructing the user/agent how to configure it.
    """
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        binder_outline = db.get_outline()
    except Exception as e:
        raise ValueError(f"Error parsing Scrivener project at '{project_path}': {e}. Please ensure the path is correct and contains a valid .scriv folder structure.")
    agent_workspace = None
    for node in binder_outline:
        if '[agent workspace]' in node.get('title', '').lower():
            agent_workspace = node
            break
    if not agent_workspace:
        raise ValueError("No '[Agent Workspace]' folder found in Scrivener project. Please run the 'create_agent_workspace' tool on this project first to set up binder templates and settings.")
    pd_node = None
    for child in agent_workspace.get('children', []):
        if child.get('title', '').lower() == 'prompt directives':
            pd_node = child
            break
    if not pd_node:
        raise ValueError("No 'Prompt Directives' document found under '[Agent Workspace]' folder. Please ensure it exists so model configuration can be parsed.")
    files_data = db.read_scene(pd_node['uuid'])
    notes = files_data.get('notes', '')
    if not notes.strip():
        raise ValueError("The 'Prompt Directives' document Notes are empty. To configure a model, please insert the following metadata table in the document notes:\n\n### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| Model | anthropic/claude-3.5-sonnet |\n")
    sections = parse_section_tables(notes)
    meta_table = next((rows for heading, rows in sections.items() if 'agent metadata' in heading or 'metadata' in heading), [])
    if not meta_table:
        raise ValueError("No '### Agent Metadata' or '### Metadata' section table was found in 'Prompt Directives' notes. Please add a table configured like this in the notes:\n\n### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| Model | anthropic/claude-3.5-sonnet |\n")
    metadata = extract_metadata_from_table(meta_table)
    meta_clean = {k.lower().replace(' ', '_'): v.strip() for k, v in metadata.items()}
    selected_model = None
    if task_type == 'drafting':
        for key in ['drafting_model', 'prose_model', 'writer_model', 'writing_model']:
            if key in meta_clean and meta_clean[key]:
                selected_model = meta_clean[key]
                break
    elif task_type == 'critique':
        for key in ['critique_model', 'editor_model', 'analyzer_model', 'analysis_model']:
            if key in meta_clean and meta_clean[key]:
                selected_model = meta_clean[key]
                break
    if not selected_model:
        for key in ['model', 'default_model']:
            if key in meta_clean and meta_clean[key]:
                selected_model = meta_clean[key]
                break
    if not selected_model:
        raise ValueError(f"No suitable model setting found in '### Agent Metadata' table for task '{task_type or 'default'}'. Please specify a 'Model' or a task-specific model attribute in the table, e.g.:\n\n### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| Model | anthropic/claude-3.5-sonnet |\n| Drafting Model | anthropic/claude-3.5-sonnet |\n| Critique Model | google/gemini-2.5-pro |\n")
    return selected_model

def call_ai_model(system_prompt: str, user_prompt: str, model_string: str=None, project_path: str=None) -> str:
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'call_ai_model'):
        func = server_mod.call_ai_model
        if func is not call_ai_model:
            return func(system_prompt, user_prompt, model_string, project_path)
    return _impl_call_ai_model(system_prompt, user_prompt, model_string, project_path)

def _impl_call_ai_model(system_prompt: str, user_prompt: str, model_string: str=None, project_path: str=None) -> str:
    load_env_file(project_path)
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY is not set in the environment or .env file. Please copy '.env.example' to '.env' and provide your OpenRouter API key.")
    if not model_string:
        raise ValueError("AI model string is not set. A valid model must be configured in '[Agent Workspace] > Prompt Directives' notes.")
    url = 'https://openrouter.ai/api/v1/chat/completions'
    headers = {'Authorization': f'Bearer {openrouter_key}', 'Content-Type': 'application/json', 'HTTP-Referer': 'https://github.com/schefflerjens/homer', 'X-Title': 'Homer Writer Assistant'}
    payload = {'model': model_string, 'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}], 'temperature': 0.7}
    try:
        context = ssl._create_unverified_context()
    except AttributeError:
        context = None
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, context=context) as response:
            raw_body = response.read().decode('utf-8')
            clean_body = raw_body.strip()
            try:
                res_data = json.loads(clean_body)
            except json.JSONDecodeError as jde:
                sys.stderr.write(f'JSON decode failed. Raw response length: {len(raw_body)}. First 200 chars: {repr(raw_body[:200])}. Error: {jde}\n')
                sys.stderr.flush()
                raise RuntimeError(f'Failed to decode JSON from OpenRouter response: {jde}. Raw body snippet: {repr(clean_body[:200])}')
            if 'error' in res_data:
                err_msg = res_data['error'].get('message', 'Unknown OpenRouter Error')
                raise RuntimeError(f'OpenRouter API returned error: {err_msg}')
            choices = res_data.get('choices')
            if not choices:
                raise RuntimeError(f'OpenRouter API returned an empty or invalid response structure: {res_data}')
            first_choice = choices[0]
            message = first_choice.get('message')
            if not message:
                raise RuntimeError(f'OpenRouter API choice does not contain a message: {first_choice}')
            text = message.get('content')
            if text is None or not text.strip():
                finish_reason = first_choice.get('finish_reason', 'unknown')
                raise RuntimeError(f"OpenRouter API returned an empty response. Finish reason: '{finish_reason}'. This can happen due to safety filters, billing/credit issues, context length limits, or OpenRouter routing issues.")
            return text
    except Exception as e:
        sys.stderr.write(f"OpenRouter API call failed for model '{model_string}': {e}\n")
        sys.stderr.flush()
        raise e

def get_project_genre_benchmarks(project_path: str) -> dict:
    server_mod = sys.modules.get('mcp_server.server')
    if server_mod and hasattr(server_mod, 'get_project_genre_benchmarks'):
        func = server_mod.get_project_genre_benchmarks
        if func is not get_project_genre_benchmarks:
            return func(project_path)
    return _impl_get_project_genre_benchmarks(project_path)

def _impl_get_project_genre_benchmarks(project_path: str) -> dict:
    """
    Finds genre and metrics benchmarks from Prompt Directives, Craft Brief, or Genre Guide in Scrivener.
    Returns a dict with targets.
    """
    genre = 'general fiction'
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        binder_outline = db.get_outline()
    except Exception:
        return GENRE_PRESETS['general fiction'].copy()
    pd_node = None
    for root_node in binder_outline:

        def find_node(node, title):
            if not node:
                return None
            if (node.get('title') or '').lower() == title:
                return node
            for child in node.get('children') or []:
                res = find_node(child, title)
                if res:
                    return res
            return None
        pd_node = find_node(root_node, 'prompt directives')
        if pd_node:
            break
    explicit_benchmarks = {}
    if pd_node:
        try:
            pd_scene = db.read_scene(pd_node['uuid'])
            notes = pd_scene.get('notes', '')
            if notes.strip():
                sections = parse_section_tables(notes)
                for heading, rows in sections.items():
                    hl = heading.lower()
                    if 'benchmark' in hl or 'metadata' in hl:
                        metadata = extract_metadata_from_table(rows)
                        explicit_benchmarks.update({k.lower().replace(' ', '_'): v for k, v in metadata.items()})
        except Exception:
            pass
    explicit_genre = explicit_benchmarks.get('genre', explicit_benchmarks.get('target_genre', ''))
    if explicit_genre:
        genre = explicit_genre.lower()
    else:
        target_doc = None
        for root_node in binder_outline:

            def find_target_doc(node):
                if not node:
                    return None
                title = (node.get('title') or '').lower()
                if 'genre guide' in title or 'craft brief' in title or 'writing instructions' in title:
                    return node
                for child in node.get('children') or []:
                    res = find_target_doc(child)
                    if res:
                        return res
                return None
            target_doc = find_target_doc(root_node)
            if target_doc:
                break
        if target_doc:
            try:
                target_scene = db.read_scene(target_doc['uuid'])
                doc_text = target_scene.get('text', '').lower()
                if 'middle grade' in doc_text or 'mg' in doc_text:
                    genre = 'middle grade'
                elif 'young adult' in doc_text or 'ya' in doc_text:
                    genre = 'young adult'
            except Exception:
                pass
    base_genre = 'general fiction'
    if 'middle' in genre or 'mg' in genre:
        base_genre = 'middle grade'
    elif 'young' in genre or 'ya' in genre:
        base_genre = 'young adult'
    preset = GENRE_PRESETS[base_genre].copy()

    def clean_float(val):
        if not val:
            return None
        cleaned = re.sub('[^\\d.]', '', val)
        try:
            return float(cleaned)
        except ValueError:
            return None
    override_grade = explicit_benchmarks.get('target_grade_level', explicit_benchmarks.get('grade_level', ''))
    if override_grade:
        v = clean_float(override_grade)
        if v is not None:
            preset['grade_level_min'] = max(0.0, v - 1.0)
            preset['grade_level_max'] = v + 1.0
    override_adverb = explicit_benchmarks.get('max_adverb_density', explicit_benchmarks.get('max_adverbs', ''))
    if override_adverb:
        v = clean_float(override_adverb)
        if v is not None:
            preset['max_adverb_density'] = v
    override_passive = explicit_benchmarks.get('max_passive_density', explicit_benchmarks.get('max_passive', ''))
    if override_passive:
        v = clean_float(override_passive)
        if v is not None:
            preset['max_passive_density'] = v
    override_filler = explicit_benchmarks.get('max_filler_density', explicit_benchmarks.get('max_filler', ''))
    if override_filler:
        v = clean_float(override_filler)
        if v is not None:
            preset['max_filler_density'] = v
    return preset

