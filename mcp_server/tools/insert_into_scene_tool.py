import os
import re

from mcp_server.engine.book_engine import ensure_safe_to_write, get_book_db
from mcp_server.mcp_server import server
from mcp_server.prompt_loader import load_prompt
from mcp_server.server_utils import call_ai_model, get_project_model_setting


@server.register_tool(name='insert_into_scene', description="Inserts AI-generated prose immediately following a unique anchor text block inside an existing Scrivener scene draft, using the project's calibrated writer engine.", schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the Scrivener (.scriv) project package'}, 'scene_uuid': {'type': 'string', 'description': 'UUID of the target scene document'}, 'after_text': {'type': 'string', 'description': 'A unique contiguous block of text from the scene draft. The generated prose will be inserted immediately after this text. Must match exactly.'}, 'custom_instructions': {'type': 'string', 'description': 'Optional style steering for the generated segment', 'default': None}}, 'required': ['project_path', 'scene_uuid', 'after_text']})
def insert_into_scene_tool(project_path: str, scene_uuid: str, after_text: str, custom_instructions: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        ensure_safe_to_write(expanded_path)
        db = get_book_db(expanded_path)
        scene_data = db.read_scene(scene_uuid)
        draft_text = scene_data.get('text', '')
        if not draft_text.strip():
            return {'content': [{'type': 'text', 'text': 'Error: Scene draft text is empty. Cannot perform insertion.'}], 'isError': True}
        count = draft_text.count(after_text)
        if count == 0:
            return {'content': [{'type': 'text', 'text': f"Error: The target text '{after_text}' was not found in the scene draft."}], 'isError': True}
        elif count > 1:
            return {'content': [{'type': 'text', 'text': f"Error: Multiple matches ({count}) for target text '{after_text}' were found. Please provide more surrounding context to ensure a unique match."}], 'isError': True}
        before_part, after_part = draft_text.split(after_text, 1)
        before_paragraphs = [p.strip() for p in before_part.split('\n\n') if p.strip()]
        context_before = '\n\n'.join(before_paragraphs[-5:]) if before_paragraphs else ''
        after_paragraphs = [p.strip() for p in after_part.split('\n\n') if p.strip()]
        context_after = '\n\n'.join(after_paragraphs[:5]) if after_paragraphs else ''
        surrounding_text_list = []
        if context_before:
            surrounding_text_list.append(context_before)
        surrounding_text_list.append(after_text)
        if context_after:
            surrounding_text_list.append(context_after)
        surrounding_text_str = '\n\n'.join(surrounding_text_list)
        style_directives_content = ''
        pd_node = None
        binder_outline = db.get_outline()
        agent_workspace = None
        for node in binder_outline:
            if '[agent workspace]' in node.get('title', '').lower():
                agent_workspace = node
                break
        if agent_workspace:
            for child in agent_workspace.get('children', []):
                if child.get('title', '').lower() == 'prompt directives':
                    pd_node = child
                    break
        if not pd_node:

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
            for root_node in binder_outline:
                pd_node = find_node(root_node, 'prompt directives')
                if pd_node:
                    break
        if pd_node:
            try:
                pd_files = db.read_scene(pd_node['uuid'])
                text_content = pd_files.get('text', '').strip()
                notes_content = pd_files.get('notes', '').strip()
                if notes_content:
                    style_directives_content = notes_content
                else:
                    style_directives_content = text_content
            except Exception:
                pass
        if not style_directives_content.strip():
            style_directives_content = '# Style Guide & Prompt Directives\n- POV: Third Person Limited\n- Tense: Past Tense'
        characters_nodes = []
        for root_node in binder_outline:

            def find_all_char_folders(node):
                if not node:
                    return
                if (node.get('title') or '').lower() == 'characters':
                    characters_nodes.append(node)
                for child in node.get('children') or []:
                    find_all_char_folders(child)
            find_all_char_folders(root_node)
        character_facts = []

        def collect_character_texts(node):
            n_type = node.get('type', 'Text')
            if n_type == 'Text':
                try:
                    char_files = db.read_scene(node['uuid'])
                    char_text = char_files.get('text', '').strip()
                    char_notes = char_files.get('notes', '').strip()
                    title = node.get('title') or 'Unnamed Character'
                    facts = []
                    if char_text:
                        facts.append(char_text)
                    if char_notes:
                        facts.append(char_notes)
                    if facts:
                        facts_str = ' '.join(facts).replace('\n', ' ').strip()
                        facts_str = ' '.join(facts_str.split())
                        character_facts.append(f'{title}: {facts_str}')
                except Exception:
                    pass
            for child in node.get('children') or []:
                collect_character_texts(child)
        for char_folder in characters_nodes:
            for child in char_folder.get('children') or []:
                collect_character_texts(child)
        character_constraints_str = '\n'.join(character_facts) if character_facts else 'None defined.'
        scene_synopsis = scene_data.get('synopsis', '')
        scene_notes = scene_data.get('notes', '')
        timeline_position = 'None defined.'
        pov_knowledge = 'None defined.'
        if scene_notes:
            timeline_match = re.search('(?:Timeline Position|Timeline|Has Happened So Far):\\s*(.*)', scene_notes, re.IGNORECASE)
            if timeline_match:
                timeline_position = timeline_match.group(1).strip()
            knowledge_match = re.search("(?:POV Knowledge|Current Knowledge|POV character\\'s current knowledge|POV character\\'s knowledge):\\s*(.*)", scene_notes, re.IGNORECASE)
            if knowledge_match:
                pov_knowledge = knowledge_match.group(1).strip()
            if not timeline_match and (not knowledge_match):
                timeline_position = scene_notes.strip()
                pov_knowledge = 'Refer to Timeline position / Scene Notes.'
        context_block = f"## PROJECT CONTEXT\n### Style Directives\n{style_directives_content}\n\n### Character Constraints\n{character_constraints_str}\n\n### Scene Context\nSynopsis: {scene_synopsis or 'None defined.'}\nTimeline position: {timeline_position}\nPOV character's current knowledge: {pov_knowledge}\n\n### Surrounding Text\n{surrounding_text_str}"
        model_string = get_project_model_setting(expanded_path, task_type='drafting')
        system_prompt = load_prompt('insert_into_scene_system.txt')
        user_prompt = load_prompt('insert_into_scene_user.txt').replace('{context_block}', context_block).replace('{custom_instructions}', custom_instructions or 'Continue the scene narrative naturally.')
        generated_prose = call_ai_model(system_prompt, user_prompt, model_string, expanded_path)
        if not generated_prose or not generated_prose.strip():
            return {'content': [{'type': 'text', 'text': 'Error: AI returned an empty insertion draft.'}], 'isError': True}
        snapshot_description = 'before the edit'
        try:
            db.create_scene_snapshot(scene_uuid, snapshot_description)
            snapshot_status = f"✅ Native Scrivener XML snapshot backup created successfully: '{snapshot_description}'."
        except Exception as e:
            snapshot_status = f'⚠️ Warning: Failed to create native XML snapshot: {e}. Editing anyway.'
        generated_prose = generated_prose.strip()
        whitespace_after = ''
        i = 0
        while i < len(after_part) and after_part[i].isspace():
            whitespace_after += after_part[i]
            i += 1
        remaining_after_part = after_part[i:]
        if '\n' in whitespace_after:
            updated_text = before_part + after_text + '\n\n' + generated_prose + '\n\n' + remaining_after_part
        else:
            sep_before = ' ' if not after_text[-1].isspace() else ''
            sep_after = ' ' if remaining_after_part and (not remaining_after_part[0].isspace()) else ''
            updated_text = before_part + after_text + sep_before + generated_prose + sep_after + remaining_after_part
        db.write_scene(scene_uuid, text=updated_text, notes=scene_data.get('notes'), synopsis=scene_data.get('synopsis'))
        return {'content': [{'type': 'text', 'text': f'Successfully inserted prose into scene!\n\n{snapshot_status}\nInserted Prose:\n{generated_prose}\n\nUpdated scene saved in Scrivener.'}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error inserting into scene: {str(e)}'}], 'isError': True}
