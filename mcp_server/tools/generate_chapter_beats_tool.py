import json
import os
import traceback

from mcp_server.book_codex import (
    parse_codex,
)
from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server
from mcp_server.prompt_loader import load_prompt
from mcp_server.server_utils import call_ai_model, get_project_model_setting


@server.register_tool(name='generate_chapter_beats', description='Takes a high-level chapter synopsis/premise in Scrivener, partitions it into specific scenes via LLM, and automatically creates the scene documents under that chapter folder, writing their generated beats into their binder synopses.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the target .scriv project package'}, 'chapter_folder_uuid': {'type': 'string', 'description': 'The unique UUID of the parent Chapter folder binder item'}, 'num_scenes': {'type': 'integer', 'description': 'The number of scenes to generate. Defaults to 3.', 'default': 3}, 'current_act': {'type': 'string', 'description': "Optional act/segment (e.g. 'Act 1') to filter chronological Codex timeline states"}, 'custom_beats_prompt': {'type': 'string', 'description': 'Optional specific constraints or themes to enforce in the generated scene outline beats'}}, 'required': ['project_path', 'chapter_folder_uuid']})
def generate_chapter_beats_tool(project_path: str, chapter_folder_uuid: str, num_scenes: int=3, current_act: str=None, custom_beats_prompt: str=None) -> dict:
    ensure_safe_to_write(project_path)
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        chapter_files = db.read_scene(chapter_folder_uuid)
        chapter_synopsis = chapter_files.get('synopsis', '').strip()
        outline = db.get_outline()

        def find_node_by_uuid(nodes, target_uuid):
            for n in nodes:
                if n['uuid'] == target_uuid:
                    return n
                res = find_node_by_uuid(n.get('children', []), target_uuid)
                if res:
                    return res
            return None
        chapter_node = find_node_by_uuid(outline, chapter_folder_uuid)
        chapter_title = chapter_node['title'] if chapter_node else 'Chapter'
        is_folder = chapter_node['type'] == 'Folder' if chapter_node else True
        if not chapter_synopsis:
            item_type_label = 'chapter folder' if is_folder else 'scene document'
            return {'content': [{'type': 'text', 'text': f"Error: The {item_type_label} '{chapter_title}' (UUID: {chapter_folder_uuid}) does not have a synopsis. Please write a high-level synopsis/premise in Scrivener first so the AI can partition it!"}], 'isError': True}
        codex_db = parse_codex(expanded_path, current_act=current_act)
        available_characters = []
        available_places = []
        if codex_db:
            available_characters = [c.get('title') for c in codex_db.get('characters', []) if c.get('title')]
            available_places = [p.get('title') for p in codex_db.get('places', []) if p.get('title')]
        available_characters_str = ', '.join(available_characters) if available_characters else '[No characters defined in Codex yet]'
        available_locations_str = ', '.join(available_places) if available_places else '[No locations defined in Codex yet]'
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        if not is_folder:
            system_prompt = load_prompt('scene_beats_system.txt')
            user_prompt = load_prompt('scene_beats_user.txt').replace('{scene_title}', chapter_title).replace('{scene_synopsis}', chapter_synopsis).replace('{available_characters}', available_characters_str).replace('{available_locations}', available_locations_str)
            if custom_beats_prompt:
                user_prompt += f'\n\n**Additional Planning Directives:** {custom_beats_prompt}'
            generated_text = call_ai_model(system_prompt, user_prompt, model_string=model_string, project_path=expanded_path)
            beats_content = generated_text.strip()
            db.write_scene(chapter_folder_uuid, synopsis=beats_content)
            result_payload = {'status': 'success', 'item_type': 'scene', 'scene_title': chapter_title, 'uuid': chapter_folder_uuid, 'generated_beats': beats_content}
            return {'content': [{'type': 'text', 'text': json.dumps(result_payload, indent=2)}]}
        existing_scenes = []
        if chapter_node:
            for child in chapter_node.get('children', []):
                if child.get('type') == 'Text':
                    existing_scenes.append(child)
        if existing_scenes:
            num_scenes = len(existing_scenes)
            existing_scenes_context = 'The chapter folder already contains these scene documents:\n'
            for idx, s in enumerate(existing_scenes):
                existing_scenes_context += f"- Scene {idx + 1}: {s['title']} (UUID: {s['uuid']})\n"
            existing_scenes_context += 'Please structure your partitioning to match these existing scenes in order. Return exactly the same titles or match them closely.\n'
        else:
            existing_scenes_context = ''

        def find_preceding_chapter(nodes, target_uuid):
            parent_list = [None]

            def traverse(items):
                for item in items:
                    if item['uuid'] == target_uuid:
                        parent_list[0] = items
                        return True
                    if traverse(item.get('children', [])):
                        return True
                return False
            traverse(nodes)
            if parent_list[0]:
                lst = parent_list[0]
                target_idx = -1
                for i, item in enumerate(lst):
                    if item['uuid'] == target_uuid:
                        target_idx = i
                        break
                if target_idx > 0:
                    for i in range(target_idx - 1, -1, -1):
                        prev_item = lst[i]
                        if prev_item.get('type') == 'Folder':
                            return prev_item
            return None
        prev_chapter_node = find_preceding_chapter(outline, chapter_folder_uuid)
        prev_chapter_context = ''
        if prev_chapter_node:
            try:
                prev_synopsis = db.read_scene(prev_chapter_node['uuid']).get('synopsis', '').strip()
                if prev_synopsis:
                    prev_chapter_context = f"## Previous Chapter Context ('{prev_chapter_node['title']}'):\n{prev_synopsis}\n"
            except Exception:
                pass
        system_prompt = load_prompt('chapter_beats_system.txt')
        user_prompt = load_prompt('chapter_beats_user.txt').replace('{chapter_title}', chapter_title).replace('{chapter_synopsis}', chapter_synopsis).replace('{preceding_chapter_context}', prev_chapter_context).replace('{existing_scenes_context}', existing_scenes_context).replace('{available_characters}', available_characters_str).replace('{available_locations}', available_locations_str).replace('{num_scenes}', str(num_scenes))
        if custom_beats_prompt:
            user_prompt += f'\n\n**Additional Planning Directives:** {custom_beats_prompt}'
        generated_text = call_ai_model(system_prompt, user_prompt, model_string=model_string, project_path=expanded_path)
        json_text = generated_text.strip()
        if json_text.startswith('```'):
            parts = json_text.split('```')
            if len(parts) >= 3:
                json_text = parts[1]
            else:
                json_text = parts[0].lstrip('`')
            if json_text.startswith('json'):
                json_text = json_text[4:]
        json_text = json_text.strip()
        scenes_list = json.loads(json_text)
        created_scenes = []
        for idx, scene_data in enumerate(scenes_list):
            s_title = scene_data.get('title', f'Scene {idx + 1}')
            s_synopsis = scene_data.get('synopsis', '')
            if idx < len(existing_scenes):
                target_scene = existing_scenes[idx]
                db.write_scene(target_scene['uuid'], synopsis=s_synopsis)
                created_scenes.append({'title': target_scene['title'], 'uuid': target_scene['uuid'], 'synopsis': s_synopsis, 'present_characters': scene_data.get('present_characters', [])})
            else:
                full_scene_title = f'Scene {idx + 1}: {s_title}'
                new_scene_uuid = db.create_binder_item(chapter_folder_uuid, full_scene_title, item_type='Text')
                db.write_scene(new_scene_uuid, text='', notes='', synopsis=s_synopsis)
                created_scenes.append({'title': full_scene_title, 'uuid': new_scene_uuid, 'synopsis': s_synopsis, 'present_characters': scene_data.get('present_characters', [])})
        result_payload = {'status': 'success', 'chapter_title': chapter_title, 'scenes_created_count': len(created_scenes), 'scenes': created_scenes}
        return {'content': [{'type': 'text', 'text': json.dumps(result_payload, indent=2)}]}
    except Exception as e:
        tb = traceback.format_exc()
        return {'content': [{'type': 'text', 'text': f'Error generating chapter beats: {str(e)}\nTraceback:\n{tb}'}], 'isError': True}
