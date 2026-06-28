import os

from mcp_server.engine.book_engine import get_book_db
from mcp_server.mcp_server import server
from mcp_server.prompt_loader import load_prompt
from mcp_server.readability import compute_readability_metrics
from mcp_server.server_utils import (
    GENRE_PRESETS,
    call_ai_model,
    get_project_genre_benchmarks,
    get_project_model_setting,
)


@server.register_tool(name='generate_chapter_critique', description='Generates a comprehensive diagnostic critique of a chapter/scene using local readability indices and style metrics compared against target genre benchmarks.', schema={'type': 'object', 'properties': {'project_path': {'type': 'string', 'description': 'Absolute path to the Scrivener (.scriv) project package'}, 'scene_uuid': {'type': 'string', 'description': 'UUID of the target Scene/Text document to analyze'}, 'target_reading_level': {'type': 'string', 'description': 'Target reading/genre level (e.g. Middle Grade, Young Adult, Adult). If not provided, dynamically discovered.', 'default': None}}, 'required': ['project_path', 'scene_uuid']})
def generate_chapter_critique(project_path: str, scene_uuid: str, target_reading_level: str=None) -> dict:
    try:
        expanded_path = os.path.expanduser(project_path)
        db = get_book_db(expanded_path)
        scene_data = db.read_scene(scene_uuid)
        draft_text = scene_data.get('text', '')
        if not draft_text.strip():
            return {'content': [{'type': 'text', 'text': 'Scene draft text is empty. Nothing to analyze.'}]}
        metrics = compute_readability_metrics(draft_text)
        benchmarks = get_project_genre_benchmarks(expanded_path)
        if target_reading_level:
            base = target_reading_level.lower()
            if 'middle' in base or 'mg' in base:
                benchmarks = GENRE_PRESETS['middle grade'].copy()
            elif 'young' in base or 'ya' in base:
                benchmarks = GENRE_PRESETS['young adult'].copy()
            else:
                benchmarks = GENRE_PRESETS['general fiction'].copy()
        grade = metrics['flesch_kincaid_grade']
        reading_ease = metrics['flesch_reading_ease']
        sentence_length = metrics['average_sentence_length']
        adverbs = metrics['adverb_density']
        passive = metrics['passive_voice_density']
        fillers = metrics['filler_word_density']
        scorecard = f"### 📊 Prose Diagnostic Scorecard ({benchmarks['genre']} Benchmarks)\n\n| Metric | Actual | Target / Benchmark | Status |\n| --- | --- | --- | --- |\n| **Grade Level (FKGL)** | {grade} | {benchmarks['grade_level_min']} - {benchmarks['grade_level_max']} | {('✅ Optimal' if benchmarks['grade_level_min'] <= grade <= benchmarks['grade_level_max'] else '⚠️ Out of Bounds')} |\n| **Reading Ease (FRE)** | {reading_ease} | 50.0 - 90.0 | {('✅ Optimal' if 50.0 <= reading_ease <= 90.0 else '⚠️ Complex Prose')} |\n| **Avg Sentence Length** | {sentence_length} words | {benchmarks['avg_sentence_length_min']} - {benchmarks['avg_sentence_length_max']} | {('✅ Optimal' if benchmarks['avg_sentence_length_min'] <= sentence_length <= benchmarks['avg_sentence_length_max'] else '⚠️ Monotone/Long')} |\n| **Adverb Density** | {adverbs}% | <= {benchmarks['max_adverb_density']}% | {('✅ Optimal' if adverbs <= benchmarks['max_adverb_density'] else '⚠️ Overuse of Adverbs')} |\n| **Passive Voice** | {passive}% | <= {benchmarks['max_passive_density']}% | {('✅ Optimal' if passive <= benchmarks['max_passive_density'] else '⚠️ Overuse of Passives')} |\n| **Filler Word Density** | {fillers}% | <= {benchmarks['max_filler_density']}% | {('✅ Optimal' if fillers <= benchmarks['max_filler_density'] else '⚠️ Overuse of Fillers')} |\n\n"
        repeats_section = '### 🔄 Word & Phrase Repetition\n\n'
        repeats_section += '**Top Repeated Content Words:**\n'
        word_runs = [f'`{w}` ({c}x)' for w, c in metrics['top_repeated_words'][:8]]
        repeats_section += ', '.join(word_runs) + '\n\n'
        repeats_section += '**Repeated 3-Word Phrases:**\n'
        if metrics['repeated_phrases']['3_grams']:
            phrases = [f'"*{ph}*" ({c}x)' for ph, c in metrics['repeated_phrases']['3_grams'][:5]]
            repeats_section += ', '.join(phrases) + '\n\n'
        else:
            repeats_section += '*None detected*\n\n'
        repeats_section += '**Repeated 4-Word Phrases:**\n'
        if metrics['repeated_phrases']['4_grams']:
            phrases = [f'"*{ph}*" ({c}x)' for ph, c in metrics['repeated_phrases']['4_grams'][:5]]
            repeats_section += ', '.join(phrases) + '\n\n'
        else:
            repeats_section += '*None detected*\n\n'
        style_guide = ''
        pd_node = None
        for root_node in db.get_outline():

            def find_node(node, title):
                if node.get('title', '').lower() == title:
                    return node
                for child in node.get('children', []):
                    res = find_node(child, title)
                    if res:
                        return res
                return None
            pd_node = find_node(root_node, 'prompt directives')
            if pd_node:
                break
        if pd_node:
            try:
                style_guide = db.read_scene(pd_node['uuid']).get('text', '')
            except Exception:
                pass
        model_string = get_project_model_setting(expanded_path, task_type='critique')
        system_prompt = load_prompt('chapter_critique_system.txt')
        user_prompt = load_prompt('chapter_critique_user.txt').replace('{scorecard}', scorecard).replace('{repeats_section}', repeats_section).replace('{style_guide}', style_guide[:1000]).replace('{draft_text}', draft_text[:6000])
        critique_text = call_ai_model(system_prompt, user_prompt, model_string, expanded_path)
        full_report = f"# Standardized Chapter Critique: {scene_data.get('title', 'Draft Scene')}\n\n{scorecard}{repeats_section}## 📝 Editorial Diagnosis\n\n{critique_text}"
        return {'content': [{'type': 'text', 'text': full_report}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error generating critique: {str(e)}'}], 'isError': True}
