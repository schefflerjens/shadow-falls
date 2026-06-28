import json
import os
import shutil
import tempfile
import unittest

from mcp_server.engine.in_memory_engine import InMemoryDb

FakeBookDb = InMemoryDb

class FakeDbTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        FakeBookDb._registry.clear()
        shutil.rmtree(self.temp_dir)

class TestReadabilityStyleMetrics(unittest.TestCase):
    def test_readability_and_syllables(self):
        from mcp_server.readability import compute_readability_metrics, count_syllables
        
        # Test syllable counting
        self.assertEqual(count_syllables("fox"), 1)
        self.assertEqual(count_syllables("quick"), 1)
        self.assertEqual(count_syllables("lazy"), 2)
        self.assertEqual(count_syllables("table"), 2)     # Ends in consonant + le
        self.assertEqual(count_syllables("game"), 1)      # Silent e
        self.assertEqual(count_syllables("waited"), 2)    # Preceded by t
        self.assertEqual(count_syllables("needed"), 2)    # Preceded by d
        self.assertEqual(count_syllables("played"), 1)    # Silent ed
        self.assertEqual(count_syllables("lived"), 1)     # Silent ed
        
        # Test metrics calculations on simple text
        text = "The quick brown fox jumps over the lazy dog."
        metrics = compute_readability_metrics(text)
        self.assertEqual(metrics["total_words"], 9)
        self.assertEqual(metrics["total_sentences"], 1)
        self.assertGreater(metrics["flesch_reading_ease"], 0)
        self.assertLessEqual(metrics["flesch_reading_ease"], 100)
        
    def test_adverb_detector(self):
        from mcp_server.readability import compute_readability_metrics
        
        # "silly" and "friendly" are exceptions; "quickly" and "slowly" are adverbs
        text = "He walked slowly and quickly, even though he was a silly, friendly person."
        metrics = compute_readability_metrics(text)
        
        # 13 total words. "slowly" and "quickly" are the 2 matched adverbs.
        # Adverb density: (2 / 13) * 100 = 15.38%
        self.assertEqual(metrics["adverb_density"], 15.38)
        
    def test_passive_voice_detector(self):
        from mcp_server.readability import compute_readability_metrics
        
        # Active vs Passive sentences
        # Sentence 1 (Active): "He wrote the manuscript."
        # Sentence 2 (Passive): "The manuscript was written." (Passive auxiliary "was" + past participle "written")
        # Sentence 3 (Passive with adverb): "The city was quickly destroyed." (Passive auxiliary "was" + adverb + past participle "destroyed")
        text = "He wrote the manuscript. The manuscript was written. The city was quickly destroyed."
        metrics = compute_readability_metrics(text)
        
        # 3 total sentences, 2 passive voice occurrences
        # Passive density: (2 / 3) * 100 = 66.67%
        self.assertEqual(metrics["passive_voice_density"], 66.67)

        # Test cross-sentence boundaries should not match (was + stood)
        text_cross = "Butch was there. He stood."
        metrics_cross = compute_readability_metrics(text_cross)
        self.assertEqual(metrics_cross["passive_voice_density"], 0.0)

        # Test hyphenated compound adjectives should not match
        text_hyphen = "It was disc-shaped."
        metrics_hyphen = compute_readability_metrics(text_hyphen)
        self.assertEqual(metrics_hyphen["passive_voice_density"], 0.0)

        # Test aspectual/progressive verbs with adjectival participles should not match
        text_progressive = "She was getting bored."
        metrics_progressive = compute_readability_metrics(text_progressive)
        self.assertEqual(metrics_progressive["passive_voice_density"], 0.0)

        # Test stative/adjectival participle exclusions should not match
        text_stative = "The shop was closed. He was tired."
        metrics_stative = compute_readability_metrics(text_stative)
        self.assertEqual(metrics_stative["passive_voice_density"], 0.0)

        # Test modal / semi-auxiliary constructions (supposed to) should not match
        text_modal = "Things are supposed to behave."
        metrics_modal = compute_readability_metrics(text_modal)
        self.assertEqual(metrics_modal["passive_voice_density"], 0.0)

        # Test valid passive progressive should match (was being watched)
        text_pass_prog = "He was being watched."
        metrics_pass_prog = compute_readability_metrics(text_pass_prog)
        self.assertEqual(metrics_pass_prog["passive_voice_density"], 100.0)

    def test_filler_and_repetition(self):
        from mcp_server.readability import compute_readability_metrics
        
        text = "Suddenly he stood up, just because he was really very tired. He had began to think it was a very bad idea."
        metrics = compute_readability_metrics(text)
        
        # Filler words in text: "Suddenly" (1), "just" (2), "really" (3), "very" (4), "began to" (5), "very" (6)
        # Total words: 22. Filler density: (6 / 22) * 100 = 27.27%
        self.assertEqual(metrics["filler_word_density"], 27.27)
        
        # Test N-gram repetitions
        text_repeats = "The sardonic AI sat on the desk. The sardonic AI sat on the chair."
        metrics_repeats = compute_readability_metrics(text_repeats)
        
        # The 3-gram "the sardonic ai" and "sardonic ai sat" should repeat
        three_grams = [phrase for phrase, count in metrics_repeats["repeated_phrases"]["3_grams"]]
        self.assertIn("the sardonic ai", three_grams)

class TestServerCritiqueTools(FakeDbTestCase):
    def test_get_project_genre_benchmarks_default(self):
        from mcp_server.server import get_project_genre_benchmarks
        benchmarks = get_project_genre_benchmarks("/nonexistent/path")
        self.assertEqual(benchmarks["genre"], "General Adult Fiction")
        
    def test_generate_chapter_critique_and_apply(self):
        import mcp_server.server
        from mcp_server.server import (
            apply_critique_to_scene,
            generate_chapter_critique,
            get_project_genre_benchmarks,
        )
        
        db = FakeBookDb.create_new(self.temp_dir, "CritiqueBook")
        project_path = db.project_path
        db.create_agent_workspace()
        
        binder = db.get_outline()
        workspace = next(n for n in binder if "agent workspace" in n.title.lower())
        pd_node = next(n for n in workspace.children if "directives" in n.title.lower())
        
        notes_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | test/model-critique |\n\n"
            "### Genre Benchmarks\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Genre | Middle Grade |\n"
            "| Target Grade Level | 5.5 |\n"
            "| Max Adverb Density | 1.1% |\n"
        )
        db.write_scene(pd_node.uuid, text="Style guide lines.", notes=notes_table, synopsis="")
        
        benchmarks = get_project_genre_benchmarks(project_path)
        self.assertEqual(benchmarks["genre"], "Middle Grade")
        self.assertEqual(benchmarks["grade_level_max"], 6.5)
        self.assertEqual(benchmarks["max_adverb_density"], 1.1)
        
        ms_node = next(n for n in binder if n.title == "Manuscript")
        scene_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1 Scene", "Text")
        db.write_scene(
            scene_uuid, 
            text="Suddenly, he wrote the very stilted prose was written. He did it quickly.", 
            notes="", 
            synopsis="Test scene beat."
        )
        
        original_call_ai = mcp_server.server.call_ai_model
        mcp_server.server.call_ai_model = lambda *args, **kwargs: "Mocked Critique: Fix the passive structure was written."
        
        try:
            critique_res = generate_chapter_critique(project_path, scene_uuid)
            self.assertFalse(critique_res.get("isError", False))
            critique_text = critique_res["content"][0]["text"]
            self.assertIn("Prose Diagnostic Scorecard", critique_text)
            self.assertIn("Mocked Critique", critique_text)
            
            mcp_server.server.call_ai_model = lambda *args, **kwargs: "He wrote the active prose cleanly."
            
            apply_res = apply_critique_to_scene(project_path, scene_uuid, critique_text=critique_text)
            self.assertFalse(apply_res.get("isError", False))
            self.assertIn("Successfully executed style critique", apply_res["content"][0]["text"])
            
            updated_scene = db.read_scene(scene_uuid)
            self.assertEqual(updated_scene["text"].strip(), "He wrote the active prose cleanly.")
            self.assertIn("Mocked Critique", updated_scene["notes"])
            
        finally:
            mcp_server.server.call_ai_model = original_call_ai

class TestWebViewer(FakeDbTestCase):
    def test_web_viewer_lifecycle_and_apis(self):
        import urllib.parse
        import urllib.request

        import mcp_server.server
        from mcp_server.web_viewer import (
            get_server_status,
            start_server_background,
            stop_server_background,
        )
        
        test_port = 18085
        start_res = start_server_background(test_port)
        self.assertIn("Successfully started", start_res)
        
        try:
            status = get_server_status()
            self.assertEqual(status["status"], "running")
            self.assertEqual(status["port"], test_port)
            
            url = f"http://localhost:{test_port}/"
            with urllib.request.urlopen(url) as response:
                html_content = response.read().decode("utf-8")
                self.assertIn("Homer Live Chapter Web Viewer", html_content)
                self.assertIn("thumbnail-preview-card", html_content)
                
            db = FakeBookDb.create_new(self.temp_dir, "TestWebProj")
            project_path = db.project_path
            
            # Create a fake project folder structure on disk to satisfy list_books scan
            os.makedirs(project_path, exist_ok=True)
            with open(os.path.join(project_path, "TestWebProj.scrivx"), "w") as f:
                f.write("<dummy/>")
                
            db.create_agent_workspace()
            
            binder = db.get_outline()
            workspace = next(n for n in binder if "agent workspace" in n.title.lower())
            pd_node = next(n for n in workspace.children if "directives" in n.title.lower())
            
            notes_table = (
                "### Agent Metadata\n"
                "| Attribute | Value |\n"
                "| --- | --- |\n"
                "| Model | test/model-critique |\n"
            )
            db.write_scene(pd_node.uuid, text="Style guidelines.", notes=notes_table, synopsis="")
            
            ms_node = next(n for n in binder if n.title == "Manuscript")
            scene_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1 Scene", "Text")
            db.write_scene(scene_uuid, text="Select this sentence to expand. Achilles stood.", notes="", synopsis="")
            
            gitbook_path = os.path.join(self.temp_dir, "TestGitBook.gitbook")
            os.makedirs(gitbook_path, exist_ok=True)
            with open(os.path.join(gitbook_path, "binder.json"), "w") as f:
                f.write("[]")

            books_url = f"http://localhost:{test_port}/api/books?search_path={urllib.parse.quote(self.temp_dir)}"
            with urllib.request.urlopen(books_url) as response:
                books_data = json.loads(response.read().decode("utf-8"))
                self.assertTrue(isinstance(books_data, list))
                
                # Check Scrivener project
                scriv_entry = next((b for b in books_data if b["path"] == project_path), None)
                self.assertIsNotNone(scriv_entry)
                self.assertEqual(scriv_entry["name"], "TestWebProj")
                self.assertEqual(scriv_entry["format"], "scrivener")
                
                # Check GitBook project
                gitbook_entry = next((b for b in books_data if b["path"] == gitbook_path), None)
                self.assertIsNotNone(gitbook_entry)
                self.assertEqual(gitbook_entry["name"], "TestGitBook")
                self.assertEqual(gitbook_entry["format"], "gitbook")
            
            outline_url = f"http://localhost:{test_port}/api/outline?project_path={urllib.parse.quote(project_path)}"
            with urllib.request.urlopen(outline_url) as response:
                outline_data = json.loads(response.read().decode("utf-8"))
                self.assertTrue(isinstance(outline_data, list))
                self.assertEqual(outline_data[0]["title"], "Manuscript")
                
            scene_url = f"http://localhost:{test_port}/api/scene?project_path={urllib.parse.quote(project_path)}&uuid={scene_uuid}"
            with urllib.request.urlopen(scene_url) as response:
                scene_data = json.loads(response.read().decode("utf-8"))
                self.assertEqual(scene_data["title"], "Chapter 1 Scene")
                self.assertIn("Select this sentence", scene_data["text"])
                self.assertIn("flesch_kincaid_grade", scene_data["metrics"])

            folder_url = f"http://localhost:{test_port}/api/scene?project_path={urllib.parse.quote(project_path)}&uuid={ms_node.uuid}"
            with urllib.request.urlopen(folder_url) as response:
                folder_data = json.loads(response.read().decode("utf-8"))
                self.assertEqual(folder_data["title"], "Manuscript")
                self.assertEqual(folder_data["type"], "DraftFolder")
                self.assertIn("Select this sentence", folder_data["text"])
                self.assertIn("flesch_kincaid_grade", folder_data["metrics"])
                self.assertEqual(folder_data["metrics"]["total_words"], 7)

            scorecard_url = f"http://localhost:{test_port}/api/scorecard"
            scorecard_payload = {
                "project_path": project_path,
                "scene_uuid": scene_uuid,
                "text": "This is a simple sentence. It is very short. Very short."
            }
            req = urllib.request.Request(
                scorecard_url,
                data=json.dumps(scorecard_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as response:
                scorecard_data = json.loads(response.read().decode("utf-8"))
                self.assertIn("metrics", scorecard_data)
                self.assertIn("flesch_kincaid_grade", scorecard_data["metrics"])
                self.assertEqual(scorecard_data["metrics"]["total_words"], 11)
                
            action_url = f"http://localhost:{test_port}/api/action"
            payload = {
                "project_path": project_path,
                "scene_uuid": scene_uuid,
                "action": "sensory",
                "selected_text": "Select this sentence to expand.",
                "instruction": "Make it sensory heavy"
            }
            
            original_call_ai = mcp_server.server.call_ai_model
            mcp_server.server.call_ai_model = lambda *args, **kwargs: "Enriched sensory text."
            
            try:
                req = urllib.request.Request(
                    action_url, 
                    data=json.dumps(payload).encode("utf-8"), 
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(res_data["status"], "success")
                    self.assertEqual(res_data["replacement"], "Enriched sensory text.")
                    
                disk_scene = db.read_scene(scene_uuid)
                self.assertEqual(disk_scene["text"], "Enriched sensory text. Achilles stood.")
                
                snapshot_url = f"http://localhost:{test_port}/api/snapshot"
                snap_payload = {
                    "project_path": project_path,
                    "scene_uuid": scene_uuid,
                    "description": "Test Checkpoint"
                }
                req_snap = urllib.request.Request(
                    snapshot_url,
                    data=json.dumps(snap_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req_snap) as response:
                    snap_res = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(snap_res["status"], "success")
                
                db.write_scene(scene_uuid, text="Changed after snapshot.")
                
                undo_url = f"http://localhost:{test_port}/api/undo"
                undo_payload = {
                    "project_path": project_path,
                    "scene_uuid": scene_uuid
                }
                req_undo = urllib.request.Request(
                    undo_url,
                    data=json.dumps(undo_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req_undo) as response:
                    undo_res = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(undo_res["status"], "success")
                    self.assertEqual(undo_res["title"], "Test Checkpoint")
                
                disk_scene_after_undo = db.read_scene(scene_uuid)
                self.assertEqual(disk_scene_after_undo["text"].strip(), "Enriched sensory text. Achilles stood.")
                
                save_url = f"http://localhost:{test_port}/api/save"
                save_payload = {
                    "project_path": project_path,
                    "scene_uuid": scene_uuid,
                    "text": "Manually edited content text."
                }
                req_save = urllib.request.Request(
                    save_url,
                    data=json.dumps(save_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req_save) as response:
                    save_res = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(save_res["status"], "success")
                
                disk_scene_after_save = db.read_scene(scene_uuid)
                self.assertEqual(disk_scene_after_save["text"].strip(), "Manually edited content text.")
                
            finally:
                mcp_server.server.call_ai_model = original_call_ai
                
        finally:
            stop_res = stop_server_background()
            self.assertIn("Successfully stopped", stop_res)
            
            status_after = get_server_status()
            self.assertEqual(status_after["status"], "stopped")

    def test_web_viewer_address_in_use(self):
        from mcp_server.web_viewer import (
            start_server_background,
            stop_server_background,
        )
        
        test_port = 18086
        start_res1 = start_server_background(test_port)
        self.assertIn("Successfully started", start_res1)
        
        try:
            import mcp_server.web_viewer
            original_active_server = mcp_server.web_viewer.active_server
            mcp_server.web_viewer.active_server = None
            
            try:
                start_res2 = start_server_background(test_port)
                self.assertIn("already active on port", start_res2)
                self.assertIn("address already in use", start_res2)
            finally:
                mcp_server.web_viewer.active_server = original_active_server
        finally:
            stop_server_background()

class TestMacroAnalyzer(FakeDbTestCase):
    def test_binder_scenes_extraction(self):
        from mcp_server.macro_analyzer import get_manuscript_scenes
        
        db = FakeBookDb.create_new(self.temp_dir, "TestMacroProj")
        project_path = db.project_path
        
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.title == "Manuscript")
        
        chapter_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        scene1_uuid = db.create_binder_item(chapter_uuid, "Scene 1", "Text")
        db.write_scene(scene1_uuid, text="This is scene 1 text.", notes="", synopsis="Scene 1 synopsis")
        
        scene2_uuid = db.create_binder_item(chapter_uuid, "Scene 2", "Text")
        db.write_scene(scene2_uuid, text="This is scene 2 text.", notes="", synopsis="")
        
        def exclude_node(nodes):
            for n in nodes:
                if n.uuid == scene2_uuid:
                    n.include_in_compile = False
                    return True
                if exclude_node(n.children):
                    return True
            return False
        exclude_node(db.outline)
        
        scenes = get_manuscript_scenes(project_path)
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["uuid"], scene1_uuid)
        self.assertEqual(scenes[0]["title"], "Scene 1")
        self.assertEqual(scenes[0]["chapter"], "Chapter 1")
        self.assertEqual(scenes[0]["text"], "This is scene 1 text.")
        self.assertEqual(scenes[0]["synopsis"], "Scene 1 synopsis")
        
    def test_analyze_macro_structure_tool(self):
        import mcp_server.server
        from mcp_server.server import analyze_macro_structure_tool
        
        db = FakeBookDb.create_new(self.temp_dir, "TestMacroToolProj")
        project_path = db.project_path
        db.create_agent_workspace()
        
        binder = db.get_outline()
        workspace = next(n for n in binder if "agent workspace" in n.title.lower())
        pd_node = next(n for n in workspace.children if "directives" in n.title.lower())
        notes_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | test-critique-model |\n"
        )
        db.write_scene(pd_node.uuid, text="Style guidelines.", notes=notes_table, synopsis="")
        
        ms_node = next(n for n in binder if n.title == "Manuscript")
        chapter_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        scene1_uuid = db.create_binder_item(chapter_uuid, "Scene 1", "Text")
        db.write_scene(scene1_uuid, text="First scene draft.", notes="", synopsis="Beats 1")
        
        original_call_ai = mcp_server.server.call_ai_model
        
        def mock_call_ai(system_prompt, user_prompt, model_string, project_path):
            if "JSON" in system_prompt:
                return json.dumps({
                    "scene_title": "Scene 1",
                    "outer_event": "Outer Action",
                    "writer_intent": {
                        "goal": "Active Goal",
                        "friction": "Friction",
                        "change": "Change"
                    },
                    "thematic_takeaway": "Thematic Takeaway",
                    "subplots": ["Subplot A"],
                    "timeline": {
                        "weekday": "Monday",
                        "timestamp": "Morning",
                        "weather": "Rainy",
                        "injuries": None,
                        "travel": None
                    }
                })
            else:
                return (
                    "=== MACRO-STRUCTURAL EDITORIAL ASSESSMENT ===\n"
                    "This is the developmental report.\n\n"
                    "=== OPEN ISSUES LIST ===\n"
                    "This is the list of open issues."
                )
                
        mcp_server.server.call_ai_model = mock_call_ai
        
        try:
            res = analyze_macro_structure_tool(project_path)
            self.assertFalse(res.get("isError", False))
            
            from mcp_server.server import read_editor_artifact
            sac_content = read_editor_artifact(project_path, "TestMacroToolProj_SAC_Database.json")
            assessment_content = read_editor_artifact(project_path, "TestMacroToolProj_Macro_Structural_Assessment.md")
            open_issues_content = read_editor_artifact(project_path, "TestMacroToolProj_Open_Issues_List.md")
            
            self.assertIsNotNone(sac_content)
            self.assertIsNotNone(assessment_content)
            self.assertIsNotNone(open_issues_content)
            
            sac_data = json.loads(sac_content)
            self.assertEqual(len(sac_data), 1)
            self.assertEqual(sac_data[0]["scene_title"], "Scene 1")
            self.assertEqual(sac_data[0]["timeline"]["weekday"], "Monday")
            
            # Assert "Editor" folder is created under "Notes"
            outline = db.get_outline()
            notes_node = next((n for n in outline if n.title == "Notes"), None)
            self.assertIsNotNone(notes_node)
            editor_node = next((c for c in notes_node.children if c.title == "Editor"), None)
            self.assertIsNotNone(editor_node)
        finally:
            mcp_server.server.call_ai_model = original_call_ai

    def test_simulate_ideal_reader_tool(self):
        import mcp_server.server
        from mcp_server.server import (
            read_editor_artifact,
            simulate_ideal_reader_tool,
            write_editor_artifact,
        )
        
        db = FakeBookDb.create_new(self.temp_dir, "TestIdealProj")
        project_path = db.project_path
        db.create_agent_workspace()
        
        binder = db.get_outline()
        workspace = next(n for n in binder if "agent workspace" in n.title.lower())
        pd_node = next(n for n in workspace.children if "directives" in n.title.lower())
        notes_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | test-critique-model |\n"
            "### Genre Benchmarks\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Genre | Middle Grade |\n"
        )
        db.write_scene(pd_node.uuid, text="Style guidelines.", notes=notes_table, synopsis="")
        
        # Create "Ideal Reader" document in workspace
        reader_node = db.create_binder_item(workspace.uuid, "Ideal Reader", "Text")
        db.write_scene(reader_node, text="Maya, age 10. Loves funny books.", notes="", synopsis="")
        
        ms_node = next(n for n in binder if n.title == "Manuscript")
        chapter_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        scene1_uuid = db.create_binder_item(chapter_uuid, "Scene 1", "Text")
        db.write_scene(scene1_uuid, text="First scene draft.", notes="", synopsis="Beats 1")
        
        # Write mock SAC Database to binder since it's required
        sac_data = [{
            "scene_uuid": scene1_uuid,
            "scene_title": "Scene 1",
            "outer_event": "Outer Action",
            "writer_intent": {"goal": "Goal", "friction": "Friction", "change": "Change"},
            "thematic_takeaway": "Theme",
            "subplots": [],
            "timeline": {"weekday": "Monday", "timestamp": "Morning", "weather": "Rainy", "injuries": None, "travel": None}
        }]
        write_editor_artifact(project_path, "TestIdealProj_SAC_Database.json", json.dumps(sac_data))
        
        original_call_ai = mcp_server.server.call_ai_model
        
        def mock_call_ai(system_prompt, user_prompt, model_string, project_path):
            return (
                "=== EDITORIAL LETTER ===\n"
                "This is a great editorial letter.\n\n"
                "=== INLINE COMMENTS ===\n"
                + json.dumps([
                    {
                        "scene_uuid": scene1_uuid,
                        "scene_title": "Scene 1",
                        "anchor_text": "First scene",
                        "type": "Developmental Issue",
                        "comment": "Too slow."
                    }
                ])
            )
                
        mcp_server.server.call_ai_model = mock_call_ai
        
        try:
            res = simulate_ideal_reader_tool(project_path)
            self.assertFalse(res.get("isError", False))
            
            letter_content = read_editor_artifact(project_path, "TestIdealProj_Ideal_Reader_Editorial_Letter.md")
            comments_json = read_editor_artifact(project_path, "TestIdealProj_Ideal_Reader_Inline_Comments.json")
            comments_md = read_editor_artifact(project_path, "TestIdealProj_Ideal_Reader_Inline_Comments.md")
            
            self.assertIsNotNone(letter_content)
            self.assertIsNotNone(comments_json)
            self.assertIsNotNone(comments_md)
            
            self.assertEqual(letter_content.strip(), "This is a great editorial letter.")
            comments_data = json.loads(comments_json)
            self.assertEqual(len(comments_data), 1)
            self.assertEqual(comments_data[0]["comment"], "Too slow.")
            self.assertIn("Too slow", comments_md)
            
            # Assert "Editor" folder is created under "Notes"
            outline = db.get_outline()
            notes_node = next((n for n in outline if n.title == "Notes"), None)
            self.assertIsNotNone(notes_node)
            editor_node = next((c for c in notes_node.children if c.title == "Editor"), None)
            self.assertIsNotNone(editor_node)
        finally:
            mcp_server.server.call_ai_model = original_call_ai

class TestPromptAssemblerFake(FakeDbTestCase):
    def test_prompt_assembler_compilation(self):
        from mcp_server.prompt_assembler import compile_writing_prompt
        db = FakeBookDb.create_new(self.temp_dir, "AssemblerNovel")
        project_path = db.project_path
        db.create_agent_workspace()
        binder = db.get_outline()
        
        manuscript_node = next(n for n in binder if n.title == "Manuscript")
        
        scene_1_uuid = db.create_binder_item(manuscript_node.uuid, "Scene 1", "Text")
        db.write_scene(scene_1_uuid, text="Once upon a time in Shadow Falls.", notes="", synopsis="Start of the book.")
        
        scene_2_uuid = db.create_binder_item(manuscript_node.uuid, "Scene 2", "Text")
        db.write_scene(scene_2_uuid, text="", notes="", synopsis="Jim visits the library.")
        
        workspace_item = next(item for item in binder if item.title == "[Agent Workspace]")
        codex_item = next(child for child in workspace_item.children if child.title == "Codex")
        chars_folder = next(child for child in codex_item.children if child.title == "Characters")
        places_folder = next(child for child in codex_item.children if child.title == "Places")
        
        jim_uuid = db.create_binder_item(chars_folder.uuid, "Jim", "Text")
        db.write_scene(jim_uuid, text="James the blacksmith.", notes="### Character Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Jimmy |", synopsis="")
        
        lib_uuid = db.create_binder_item(places_folder.uuid, "Library", "Text")
        db.write_scene(lib_uuid, text="Dusty town archive.", notes="### Location Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Archive, Reading Room |", synopsis="")
        
        payload = compile_writing_prompt(project_path, scene_2_uuid, current_act="Act 1")
        self.assertIn("system_prompt", payload)
        self.assertIn("user_prompt", payload)
        
        user_prompt = payload["user_prompt"]
        self.assertIn("Once upon a time in Shadow Falls.", user_prompt)
        self.assertIn("Jim visits the library.", user_prompt)
        self.assertIn("James the blacksmith.", user_prompt)
        self.assertIn("Dusty town archive.", user_prompt)
        self.assertIn(lib_uuid, payload["matched_entries_uuids"])
        self.assertIn(jim_uuid, payload["matched_entries_uuids"])

class TestOutlineFake(FakeDbTestCase):
    def test_compile_full_outline_and_character_tracking(self):
        from mcp_server.book_codex import parse_codex
        from mcp_server.book_outline import compile_full_outline
        db = FakeBookDb.create_new(self.temp_dir, "OutlineNovel")
        project_path = db.project_path
        db.create_agent_workspace()
        binder = db.get_outline()
        
        manuscript_node = next(n for n in binder if n.title == "Manuscript")
        
        workspace_item = next(item for item in binder if item.title == "[Agent Workspace]")
        codex_item = next(child for child in workspace_item.children if child.title == "Codex")
        chars_folder = next(child for child in codex_item.children if child.title == "Characters")
        places_folder = next(child for child in codex_item.children if child.title == "Places")
        
        jane_uuid = db.create_binder_item(chars_folder.uuid, "Jane", "Text")
        db.write_scene(jane_uuid, text="Jane is the hero.", notes="### Character Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Janet |", synopsis="")
        
        lib_uuid = db.create_binder_item(places_folder.uuid, "Library", "Text")
        db.write_scene(lib_uuid, text="Dusty town archive.", notes="### Location Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Archive |", synopsis="")
        
        chapter_uuid = db.create_binder_item(manuscript_node.uuid, "Chapter 1", "Folder")
        db.write_scene(chapter_uuid, text="", notes="", synopsis="Jane arrives at the town harbor.")
        
        scene_uuid = db.create_binder_item(chapter_uuid, "Scene 1.1", "Text")
        db.write_scene(scene_uuid, text="", notes="", synopsis="Jane searches the library archive.")
        
        codex_db = parse_codex(project_path)
        outline_payload = compile_full_outline(project_path, codex_db)
        
        flat_list = outline_payload["flat_list"]
        markdown = outline_payload["markdown"]
        
        self.assertEqual(len(flat_list), 3)
        
        chap_item = [f for f in flat_list if f["title"] == "Chapter 1"][0]
        self.assertEqual(chap_item["type"], "Folder")
        self.assertIn("Jane", chap_item["characters"])
        
        scene_item = [f for f in flat_list if f["title"] == "Scene 1.1"][0]
        self.assertEqual(scene_item["type"], "Text")
        self.assertIn("Jane", scene_item["characters"])
        self.assertIn("Library", scene_item["places"])
        
        self.assertIn("Chapter: Chapter 1", markdown)
        self.assertIn("Scene: Scene 1.1", markdown)
        self.assertIn("Characters:** Jane", markdown)
        self.assertIn("Places:** Library", markdown)

class TestServerHelpersFake(FakeDbTestCase):
    def test_generate_chapter_beats(self):
        import mcp_server.server
        from mcp_server.server import generate_chapter_beats_tool
        
        db = FakeBookDb.create_new(self.temp_dir, "BeatsNovel")
        project_path = db.project_path
        db.create_agent_workspace()
        binder = db.get_outline()
        
        agent_workspace = next(node for node in binder if "[agent workspace]" in node.title.lower())
        pd_node = next(child for child in agent_workspace.children if child.title.lower() == "prompt directives")
        notes_correct_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | google/gemini-2.5-pro |\n"
        )
        db.write_scene(pd_node.uuid, text="", notes=notes_correct_table, synopsis="")
        
        manuscript_node = next(n for n in binder if n.title == "Manuscript")
        
        chapter_uuid = db.create_binder_item(manuscript_node.uuid, "Chapter 1", "Folder")
        db.write_scene(chapter_uuid, text="", notes="", synopsis="Jane goes to the harbor, gets lost in the fog, and meets a sailor.")
        
        mock_response = json.dumps([
            {"title": "Arrival at docks", "synopsis": "Jane arrives at the harbor docks.", "present_characters": ["Jane"]},
            {"title": "Getting lost", "synopsis": "Jane gets lost in the heavy fog.", "present_characters": ["Jane"]},
            {"title": "The Sailor", "synopsis": "Jane meets the mysterious sailor.", "present_characters": ["Jane", "Sailor"]}
        ])
        
        original_call = mcp_server.server.call_ai_model
        mcp_server.server.call_ai_model = lambda sys, usr, *args, **kwargs: mock_response
        
        try:
            mcp_res = generate_chapter_beats_tool(project_path, chapter_uuid, num_scenes=3)
            self.assertNotIn("isError", mcp_res or {})
            
            res_data = json.loads(mcp_res["content"][0]["text"])
            self.assertEqual(res_data["status"], "success")
            self.assertEqual(res_data["scenes_created_count"], 3)
            
            updated_outline = db.get_outline()
            manuscript = next(n for n in updated_outline if n.title == "Manuscript")
            chapter_node = manuscript.children[0]
            
            self.assertEqual(len(chapter_node.children), 3)
            scene_titles = [child.title for child in chapter_node.children]
            self.assertEqual(scene_titles[0], "Scene 1: Arrival at docks")
            self.assertEqual(scene_titles[1], "Scene 2: Getting lost")
            self.assertEqual(scene_titles[2], "Scene 3: The Sailor")
            
            s1_uuid = chapter_node.children[0].uuid
            s1_data = db.read_scene(s1_uuid)
            self.assertEqual(s1_data.synopsis, "Jane arrives at the harbor docks.")
            
            s3_uuid = chapter_node.children[2].uuid
            s3_data = db.read_scene(s3_uuid)
            self.assertEqual(s3_data.synopsis, "Jane meets the mysterious sailor.")
            
        finally:
            mcp_server.server.call_ai_model = original_call

    def test_generate_chapter_beats_existing_scenes(self):
        import mcp_server.server
        from mcp_server.server import generate_chapter_beats_tool
        
        db = FakeBookDb.create_new(self.temp_dir, "BeatsNovelExisting")
        project_path = db.project_path
        db.create_agent_workspace()
        binder = db.get_outline()
        
        agent_workspace = next(node for node in binder if "[agent workspace]" in node.title.lower())
        pd_node = next(child for child in agent_workspace.children if child.title.lower() == "prompt directives")
        notes_correct_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | google/gemini-2.5-pro |\n"
        )
        db.write_scene(pd_node.uuid, text="", notes=notes_correct_table, synopsis="")
        
        manuscript_node = next(n for n in binder if n.title == "Manuscript")
        
        chapter_uuid = db.create_binder_item(manuscript_node.uuid, "Chapter 1", "Folder")
        s1_uuid = db.create_binder_item(chapter_uuid, "Docks Scene", "Text")
        s2_uuid = db.create_binder_item(chapter_uuid, "Fog Scene", "Text")
        
        db.write_scene(chapter_uuid, text="", notes="", synopsis="Jane at docks and lost.")
        db.write_scene(s1_uuid, text="", notes="", synopsis="")
        db.write_scene(s2_uuid, text="", notes="", synopsis="")
        
        mock_response = json.dumps([
            {"title": "Docks Scene", "synopsis": "Jane walks the docks.", "present_characters": ["Jane"]},
            {"title": "Fog Scene", "synopsis": "Jane is lost in fog.", "present_characters": ["Jane"]}
        ])
        
        original_call = mcp_server.server.call_ai_model
        mcp_server.server.call_ai_model = lambda sys, usr, *args, **kwargs: mock_response
        
        try:
            mcp_res = generate_chapter_beats_tool(project_path, chapter_uuid, num_scenes=2)
            self.assertNotIn("isError", mcp_res or {})
            
            updated_outline = db.get_outline()
            manuscript = next(n for n in updated_outline if n.title == "Manuscript")
            chapter_node = manuscript.children[0]
            self.assertEqual(len(chapter_node.children), 2)
            
            s1_data = db.read_scene(s1_uuid)
            self.assertEqual(s1_data.synopsis, "Jane walks the docks.")
            
            s2_data = db.read_scene(s2_uuid)
            self.assertEqual(s2_data.synopsis, "Jane is lost in fog.")
        finally:
            mcp_server.server.call_ai_model = original_call

    def test_generate_scene_beats_single(self):
        import mcp_server.server
        from mcp_server.server import generate_chapter_beats_tool
        
        db = FakeBookDb.create_new(self.temp_dir, "BeatsNovelSingle")
        project_path = db.project_path
        db.create_agent_workspace()
        binder = db.get_outline()
        
        agent_workspace = next(node for node in binder if "[agent workspace]" in node.title.lower())
        pd_node = next(child for child in agent_workspace.children if child.title.lower() == "prompt directives")
        notes_correct_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | google/gemini-2.5-pro |\n"
        )
        db.write_scene(pd_node.uuid, text="", notes=notes_correct_table, synopsis="")
        
        manuscript_node = next(n for n in binder if n.title == "Manuscript")
        
        scene_uuid = db.create_binder_item(manuscript_node.uuid, "My Scene", "Text")
        db.write_scene(scene_uuid, text="", notes="", synopsis="Jane meets the sailor in the tavern.")
        
        mock_response = "- Jane orders a drink.\n- The sailor sits next to her.\n- They discuss coordinates."
        
        original_call = mcp_server.server.call_ai_model
        mcp_server.server.call_ai_model = lambda sys, usr, *args, **kwargs: mock_response
        
        try:
            mcp_res = generate_chapter_beats_tool(project_path, scene_uuid)
            self.assertNotIn("isError", mcp_res or {})
            
            res_data = json.loads(mcp_res["content"][0]["text"])
            self.assertEqual(res_data["status"], "success")
            self.assertEqual(res_data["item_type"], "scene")
            self.assertEqual(res_data["scene_title"], "My Scene")
            self.assertEqual(res_data["generated_beats"], mock_response)
            
            scene_data = db.read_scene(scene_uuid)
            self.assertEqual(scene_data.synopsis, mock_response)
        finally:
            mcp_server.server.call_ai_model = original_call

    def test_load_env_file(self):
        from mcp_server.server import load_env_file
        
        try:
            env_file_path = os.path.join(self.temp_dir, ".env")
            with open(env_file_path, "w", encoding="utf-8") as f:
                f.write("# This is a comment\n")
                f.write("TEST_KEY_DUMMY=my_secret_key\n")
                f.write("TEST_KEY_QUOTED=\"my_quoted_key\"\n")
                
            old_cwd = os.getcwd()
            os.chdir(self.temp_dir)
            
            try:
                load_env_file()
                self.assertEqual(os.environ.get("TEST_KEY_DUMMY"), "my_secret_key")
                self.assertEqual(os.environ.get("TEST_KEY_QUOTED"), "my_quoted_key")
            finally:
                os.chdir(old_cwd)
                
        finally:
            os.environ.pop("TEST_KEY_DUMMY", None)
            os.environ.pop("TEST_KEY_QUOTED", None)
            
    def test_get_project_model_setting(self):
        from mcp_server.server import get_project_model_setting
        
        db = FakeBookDb.create_new(self.temp_dir, "ModelNovel")
        project_path = db.project_path
        
        with self.assertRaises(ValueError) as ctx:
            get_project_model_setting(project_path)
        self.assertIn("No '[Agent Workspace]' folder found", str(ctx.exception))
        
        db.create_agent_workspace()
        
        with self.assertRaises(ValueError) as ctx:
            get_project_model_setting(project_path)
        self.assertIn("notes are empty", str(ctx.exception).lower())
        
        binder = db.get_outline()
        agent_workspace = next(node for node in binder if "[agent workspace]" in node.title.lower())
        pd_node = next(child for child in agent_workspace.children if child.title.lower() == "prompt directives")
        
        notes_wrong_table = (
            "### Some Other Table\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | anthropic/claude-3.5-sonnet |\n"
        )
        db.write_scene(pd_node.uuid, text="", notes=notes_wrong_table, synopsis="")
        with self.assertRaises(ValueError) as ctx:
            get_project_model_setting(project_path)
        self.assertIn("No '### Agent Metadata' or '### Metadata' section table", str(ctx.exception))
        
        notes_correct_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | custom/model-x-large |\n"
        )
        db.write_scene(pd_node.uuid, text="", notes=notes_correct_table, synopsis="")
        
        model_setting = get_project_model_setting(project_path)
        self.assertEqual(model_setting, "custom/model-x-large")

    def test_call_ai_model_validation(self):
        import mcp_server.server
        from mcp_server.server import call_ai_model
        
        original_load_env = mcp_server.server.load_env_file
        mcp_server.server.load_env_file = lambda *args, **kwargs: None
        
        original_key = os.environ.get("OPENROUTER_API_KEY")
        if original_key is not None:
            del os.environ["OPENROUTER_API_KEY"]
            
        try:
            with self.assertRaises(ValueError) as ctx:
                call_ai_model("sys", "usr", model_string="model")
            self.assertIn("OPENROUTER_API_KEY is not set", str(ctx.exception))
            
            os.environ["OPENROUTER_API_KEY"] = "fake-key"
            
            with self.assertRaises(ValueError) as ctx:
                call_ai_model("sys", "usr", model_string=None)
            self.assertIn("AI model string is not set", str(ctx.exception))
            
        finally:
            mcp_server.server.load_env_file = original_load_env
            if original_key is not None:
                os.environ["OPENROUTER_API_KEY"] = original_key
            else:
                os.environ.pop("OPENROUTER_API_KEY", None)

    def test_call_ai_model_empty_and_invalid_responses(self):
        from unittest.mock import MagicMock, patch

        from mcp_server.server import call_ai_model
        
        original_key = os.environ.get("OPENROUTER_API_KEY")
        os.environ["OPENROUTER_API_KEY"] = "fake-key"
        
        try:
            mock_res_empty_choices = {"choices": []}
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(mock_res_empty_choices).encode("utf-8")
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                with self.assertRaises(RuntimeError) as ctx:
                    call_ai_model("sys", "usr", model_string="model")
                self.assertIn("empty or invalid response structure", str(ctx.exception))
                
            mock_res_no_message = {"choices": [{}]}
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(mock_res_no_message).encode("utf-8")
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                with self.assertRaises(RuntimeError) as ctx:
                    call_ai_model("sys", "usr", model_string="model")
                self.assertIn("choice does not contain a message", str(ctx.exception))
                
            mock_res_empty_content = {
                "choices": [{
                    "message": {"content": "   "},
                    "finish_reason": "content_filter"
                }]
            }
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(mock_res_empty_content).encode("utf-8")
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                with self.assertRaises(RuntimeError) as ctx:
                    call_ai_model("sys", "usr", model_string="model")
                self.assertIn("returned an empty response", str(ctx.exception))
                self.assertIn("content_filter", str(ctx.exception))
                
        finally:
            if original_key is not None:
                os.environ["OPENROUTER_API_KEY"] = original_key
            else:
                os.environ.pop("OPENROUTER_API_KEY", None)

    def test_list_books_with_project_roots(self):
        import json
        import os

        from mcp_server.server import list_books
        
        # Create two separate directories
        dir1 = os.path.join(self.temp_dir, "root1")
        dir2 = os.path.join(self.temp_dir, "root2")
        os.makedirs(dir1, exist_ok=True)
        os.makedirs(dir2, exist_ok=True)
        
        # Create a book in dir1
        scriv_path = os.path.join(dir1, "Book1.scriv")
        os.makedirs(scriv_path, exist_ok=True)
        with open(os.path.join(scriv_path, "Book1.scrivx"), "w") as f:
            f.write("<dummy/>")
            
        # Create a book in dir2
        gitbook_path = os.path.join(dir2, "Book2.gitbook")
        os.makedirs(gitbook_path, exist_ok=True)
        with open(os.path.join(gitbook_path, "binder.json"), "w") as f:
            f.write("[]")
            
        # Set PROJECT_ROOTS env var
        os.environ["PROJECT_ROOTS"] = f"{dir1},{dir2}"
        
        try:
            res = list_books(search_path=None)
            raw_text = res["content"][0]["text"]
            books = json.loads(raw_text)
            
            # Verify both books were found
            paths = [b["path"] for b in books]
            self.assertIn(scriv_path, paths)
            self.assertIn(gitbook_path, paths)
        finally:
            os.environ.pop("PROJECT_ROOTS", None)

class TestBulkEditingTools(FakeDbTestCase):
    def test_bulk_patch_and_regex_and_patchsets(self):
        from mcp_server.server import (
            apply_patchset_tool,
            bulk_patch_scenes_tool,
            regex_patch_scenes_tool,
        )
        
        db = FakeBookDb.create_new(self.temp_dir, "BulkEditProj")
        project_path = db.project_path
        
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.title == "Manuscript")
        chapter_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        
        scene1_uuid = db.create_binder_item(chapter_uuid, "Scene 1", "Text")
        db.write_scene(
            scene1_uuid, 
            text="This is scene 1 text. Achilles is a teddy bear. Achilles is very cool.", 
            notes="", 
            synopsis=""
        )
        
        scene2_uuid = db.create_binder_item(chapter_uuid, "Scene 2", "Text")
        db.write_scene(
            scene2_uuid, 
            text="This is scene 2 text. Achilles is in the attic.", 
            notes="", 
            synopsis=""
        )

        res = bulk_patch_scenes_tool(
            project_path=project_path,
            target_text="Achilles",
            replacement_text="Fluffy",
            scene_uuids=[scene1_uuid, scene2_uuid],
            dry_run=False
        )
        self.assertFalse(res.get("isError", False))
        self.assertIn("Successfully completed bulk patch", res["content"][0]["text"])
        self.assertIn("Scene 1", res["content"][0]["text"])
        self.assertIn("found 2 match(es)", res["content"][0]["text"])
        self.assertIn("Scene 2", res["content"][0]["text"])
        self.assertIn("found 1 match(es)", res["content"][0]["text"])

        f1 = db.read_scene(scene1_uuid)
        self.assertEqual(f1["text"], "This is scene 1 text. Fluffy is a teddy bear. Fluffy is very cool.")
        f2 = db.read_scene(scene2_uuid)
        self.assertEqual(f2["text"], "This is scene 2 text. Fluffy is in the attic.")

        self.assertTrue(scene1_uuid in db.snapshots and len(db.snapshots[scene1_uuid]) > 0)

        res_dry = bulk_patch_scenes_tool(
            project_path=project_path,
            target_text="Fluffy",
            replacement_text="Leo",
            scene_uuids=[scene1_uuid],
            dry_run=True
        )
        self.assertFalse(res_dry.get("isError", False))
        self.assertIn("[DRY RUN]", res_dry["content"][0]["text"])
        self.assertIn("found 2 match(es)", res_dry["content"][0]["text"])
        
        f1_dry = db.read_scene(scene1_uuid)
        self.assertEqual(f1_dry["text"], "This is scene 1 text. Fluffy is a teddy bear. Fluffy is very cool.")

        res_regex = regex_patch_scenes_tool(
            project_path=project_path,
            pattern=r"\bFluffy is (a|in)\b",
            replacement=r"Leo is \1",
            scene_uuids=[scene1_uuid, scene2_uuid],
            dry_run=False
        )
        self.assertFalse(res_regex.get("isError", False))
        self.assertIn("Successfully completed regex patch", res_regex["content"][0]["text"])
        
        f1_regex = db.read_scene(scene1_uuid)
        self.assertEqual(f1_regex["text"], "This is scene 1 text. Leo is a teddy bear. Fluffy is very cool.")
        f2_regex = db.read_scene(scene2_uuid)
        self.assertEqual(f2_regex["text"], "This is scene 2 text. Leo is in the attic.")

        patches = [
            {
                "type": "exact",
                "pattern": "Leo",
                "replacement": "Achilles",
                "scene_uuids": [scene1_uuid, scene2_uuid]
            },
            {
                "type": "regex",
                "pattern": r"very cool",
                "replacement": "super neat",
                "scene_uuids": [scene1_uuid]
            }
        ]
        res_set = apply_patchset_tool(
            project_path=project_path,
            patches=patches,
            dry_run=False
        )
        self.assertFalse(res_set.get("isError", False))
        self.assertIn("Successfully executed patchset batch", res_set["content"][0]["text"])

        f1_set = db.read_scene(scene1_uuid)
        self.assertEqual(f1_set["text"], "This is scene 1 text. Achilles is a teddy bear. Fluffy is super neat.")
        f2_set = db.read_scene(scene2_uuid)
        self.assertEqual(f2_set["text"], "This is scene 2 text. Achilles is in the attic.")

class TestCopyeditorTools(FakeDbTestCase):
    def test_copyediting_and_continuity_bible(self):
        import mcp_server.server
        from mcp_server.server import (
            generate_continuity_bible_tool,
            run_copyedit_audit_tool,
        )
        
        db = FakeBookDb.create_new(self.temp_dir, "CopyeditProj")
        project_path = db.project_path
        
        db.create_agent_workspace()
        
        binder = db.get_outline()
        workspace = next(n for n in binder if "agent workspace" in n.title.lower())
        pd_node = next(n for n in workspace.children if "directives" in n.title.lower())
        
        notes_table = (
            "### Agent Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Model | test-copyedit-model |\n"
            "| Style Guide | Chicago Manual of Style (CMOS) |\n"
            "| Orthography | US |\n"
        )
        db.write_scene(pd_node.uuid, text="Style directives text.", notes=notes_table, synopsis="")
        
        ms_node = next(n for n in binder if n.title == "Manuscript")
        chapter_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        scene1_uuid = db.create_binder_item(chapter_uuid, "Scene 1", "Text")
        db.write_scene(
            scene1_uuid, 
            text="This is scene 1 text. Achilles stood by the gate.", 
            notes="", 
            synopsis="Achilles waits."
        )
        
        original_call_ai = mcp_server.server.call_ai_model
        
        def mock_call_ai(system_prompt, user_prompt, model_string, project_path):
            if "extract all continuity details" in system_prompt.lower():
                return json.dumps({
                    "characters": [{"name": "Achilles", "description": "AI in teddy bear"}],
                    "settings": [{"name": "Ironworks", "description": "Abandoned factory"}],
                    "invented_terminology": [],
                    "timeline": {
                        "event": "Achilles waits at gate.",
                        "temporal_markers": "Morning",
                        "injuries_noted": "None"
                    },
                    "style_mentions": {
                        "numbers_format": "None",
                        "hyphenation": "None"
                    }
                })
            elif "merge these extractions" in system_prompt.lower():
                return json.dumps({
                    "characters": [{
                        "name": "Achilles",
                        "description": "AI in teddy bear",
                        "scenes_present": [scene1_uuid],
                        "contradictions_found": []
                    }],
                    "settings": [{
                        "name": "Ironworks",
                        "description": "Abandoned factory",
                        "scenes_present": [scene1_uuid]
                    }],
                    "invented_terminology": [],
                    "timeline": [{
                        "scene_uuid": scene1_uuid,
                        "scene_title": "Scene 1",
                        "event": "Achilles waits.",
                        "temporal_markers": "Morning",
                        "injuries_noted": "None"
                    }],
                    "style_preferences": {
                        "guide": "Chicago Manual of Style (CMOS)",
                        "orthography": "US",
                        "numbers_format": "Spell out under 100",
                        "date_format": "Month Day, Year",
                        "hyphenation_consistency": "timeline"
                    }
                })
            elif "performing a highly technical" in system_prompt.lower():
                return json.dumps([
                    {
                        "type": "Mechanical Error",
                        "description": "Missing comma in greeting.",
                        "original_text": "This is scene 1 text.",
                        "suggested_text": "This is scene 1 text, indeed."
                    }
                ])
            return ""
            
        mcp_server.server.call_ai_model = mock_call_ai
        
        try:
            res_bible = generate_continuity_bible_tool(project_path=project_path)
            self.assertFalse(res_bible.get("isError", False))
            self.assertIn("Successfully generated the Continuity Bible", res_bible["content"][0]["text"])
            self.assertIn("WARNING: You are generating a Continuity Bible before", res_bible["content"][0]["text"])
            
            from mcp_server.server import read_editor_artifact
            bible_json = read_editor_artifact(project_path, "CopyeditProj_Continuity_Bible.json")
            bible_md = read_editor_artifact(project_path, "CopyeditProj_Continuity_Bible.md")
            self.assertIsNotNone(bible_json)
            self.assertIsNotNone(bible_md)
            
            bible_data = json.loads(bible_json)
            self.assertEqual(bible_data["characters"][0]["name"], "Achilles")
                
            res_audit = run_copyedit_audit_tool(project_path=project_path)
            self.assertFalse(res_audit.get("isError", False))
            self.assertIn("Successfully completed the copyedit audit", res_audit["content"][0]["text"])
            
            audit_json = read_editor_artifact(project_path, "CopyeditProj_Copyedit_Audit.json")
            audit_md = read_editor_artifact(project_path, "CopyeditProj_Copyedit_Audit.md")
            self.assertIsNotNone(audit_json)
            self.assertIsNotNone(audit_md)
            
            audit_data = json.loads(audit_json)
            self.assertEqual(len(audit_data), 1)
            self.assertEqual(audit_data[0]["type"], "Mechanical Error")
            self.assertIn("diff", audit_data[0])
            self.assertIn("-This is scene 1 text.", audit_data[0]["diff"])
            self.assertIn("+This is scene 1 text, indeed.", audit_data[0]["diff"])
            
            # Assert "Editor" folder is created under "Notes"
            outline = db.get_outline()
            notes_node = next((n for n in outline if n.title == "Notes"), None)
            self.assertIsNotNone(notes_node)
            editor_node = next((c for c in notes_node.children if c.title == "Editor"), None)
            self.assertIsNotNone(editor_node)
        finally:
            mcp_server.server.call_ai_model = original_call_ai

class TestRenderTool(FakeDbTestCase):
    def test_render_tool_amazon_epub(self):
        # 1. Create a mock book in-memory using FakeBookDb
        db = FakeBookDb.create_new(self.temp_dir, "MyFantasyNovel")
        project_path = db.project_path
        
        # 2. Add some scenes and content to Manuscript
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.type == "DraftFolder")
        
        # Add a folder (Chapter 1)
        ch_uuid = db.create_binder_item(ms_node.uuid, "Chapter One: The Awakening", "Folder")
        
        # Add a scene
        sc_uuid = db.create_binder_item(ch_uuid, "Scene 1: Alone in the Woods", "Text")
        db.write_scene(sc_uuid, text="*It was dark in the woods.* He stood up.\n\n*   Line 1\n*   Line 2\n\n> A quote.", synopsis="Intro scene", notes="")
        
        # Add a non-compile scene (should be excluded)
        ex_uuid = db.create_binder_item(ms_node.uuid, "Research Scene", "Text")
        
        def set_include_in_compile(nodes, uuid, val):
            for n in nodes:
                if n.uuid == uuid:
                    n.include_in_compile = val
                    return True
                if set_include_in_compile(n.children, uuid, val):
                    return True
            return False
        set_include_in_compile(db.get_outline(), ex_uuid, False)
        db.write_scene(ex_uuid, text="This should be ignored.", synopsis="", notes="")
        
        # 3. Call render_tool
        from mcp_server.server import render_tool
        output_file = os.path.join(self.temp_dir, "novel.epub")
        res = render_tool(project_path, output_file, format="amazon")
        
        self.assertNotIn("isError", res)
        self.assertTrue(os.path.exists(output_file))
        
        # 4. Unpack the EPUB ZIP file and assert structural correctness
        import zipfile
        with zipfile.ZipFile(output_file, "r") as epub:
            # Check mimetype exists and is uncompressed
            info = epub.getinfo("mimetype")
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            mimetype_content = epub.read("mimetype").decode("utf-8")
            self.assertEqual(mimetype_content, "application/epub+zip")
            
            # Check container.xml
            self.assertIn("META-INF/container.xml", epub.namelist())
            container_content = epub.read("META-INF/container.xml").decode("utf-8")
            self.assertIn('rootfile full-path="OEBPS/content.opf"', container_content)
            
            # Check content.opf
            self.assertIn("OEBPS/content.opf", epub.namelist())
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")
            self.assertIn("<dc:title>MyFantasyNovel</dc:title>", opf_content)
            self.assertIn('<item id="page_1" href="page_1.xhtml"', opf_content)
            self.assertIn('<item id="page_2" href="page_2.xhtml"', opf_content)
            # Verify the research/excluded scene is NOT in the manifest
            self.assertNotIn("Research Scene", opf_content)
            
            # Verify guide block exists and is correct
            self.assertIn("<guide>", opf_content)
            self.assertIn('<reference type="cover" title="Cover" href="cover.xhtml"/>', opf_content)
            self.assertIn('<reference type="toc" title="Table of Contents" href="nav.xhtml"/>', opf_content)
            self.assertIn('<reference type="text" title="Start Reading" href="page_1.xhtml"/>', opf_content)
            
            # Check toc.ncx and nav.xhtml
            self.assertIn("OEBPS/toc.ncx", epub.namelist())
            self.assertIn("OEBPS/nav.xhtml", epub.namelist())
            
            toc_ncx_content = epub.read("OEBPS/toc.ncx").decode("utf-8")
            self.assertIn('name="dtb:depth" content="2"', toc_ncx_content)
            self.assertIn('<navPoint id="navpoint-page_1"', toc_ncx_content)
            self.assertIn('<navPoint id="navpoint-page_2"', toc_ncx_content)
            
            idx_page_1 = toc_ncx_content.find('<navPoint id="navpoint-page_1"')
            idx_page_2 = toc_ncx_content.find('<navPoint id="navpoint-page_2"')
            idx_close_page_1 = toc_ncx_content.rfind('</navPoint>')
            self.assertTrue(idx_page_1 < idx_page_2 < idx_close_page_1)
            
            nav_content = epub.read("OEBPS/nav.xhtml").decode("utf-8")
            self.assertIn('<ol>', nav_content)
            idx_ch = nav_content.find('Chapter One: The Awakening')
            idx_sc = nav_content.find('Scene 1: Alone in the Woods')
            self.assertTrue(idx_ch < idx_sc)
            
            # Verify landmarks nav block
            self.assertIn('epub:type="landmarks"', nav_content)
            self.assertIn('epub:type="cover" href="cover.xhtml"', nav_content)
            self.assertIn('epub:type="toc" href="nav.xhtml"', nav_content)
            self.assertIn('epub:type="bodymatter" href="page_1.xhtml"', nav_content)
            
            # Check stylesheet
            self.assertIn("OEBPS/stylesheet.css", epub.namelist())
            
            # Check rendered XHTML page 2 (which is Scene 1: Alone in the Woods)
            self.assertIn("OEBPS/page_2.xhtml", epub.namelist())
            page2_content = epub.read("OEBPS/page_2.xhtml").decode("utf-8")
            # Verify Markdown to XHTML conversion
            self.assertIn("<h2>Scene 1: Alone in the Woods</h2>", page2_content)
            self.assertIn("<p><em>It was dark in the woods.</em> He stood up.</p>", page2_content)
            self.assertIn("<li>Line 1</li>", page2_content)
            self.assertIn("<blockquote>", page2_content)
            self.assertIn("<p>A quote.</p>", page2_content)

    def test_render_tool_markdown(self):
        # 1. Create a mock book in-memory using FakeBookDb
        db = FakeBookDb.create_new(self.temp_dir, "MyFantasyNovel")
        project_path = db.project_path
        
        # 2. Add some scenes and content to Manuscript
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.type == "DraftFolder")
        
        # Add a folder (Chapter 1)
        ch_uuid = db.create_binder_item(ms_node.uuid, "Chapter One: The Awakening", "Folder")
        
        # Add a scene with no heading (should fall back to node title)
        sc1_uuid = db.create_binder_item(ch_uuid, "Scene 1: Alone in the Woods", "Text")
        db.write_scene(sc1_uuid, text="*It was dark in the woods.* He stood up.", synopsis="", notes="")
        
        # Add a scene with an explicit heading (should extract and use that heading)
        sc2_uuid = db.create_binder_item(ch_uuid, "Scene 2: Unnamed Originally", "Text")
        db.write_scene(sc2_uuid, text="# Scene 2: Over the Hill\n\nSome other text here.", synopsis="", notes="")
        
        # Add a scene with a duplicate title/heading to test slug uniqueness
        sc3_uuid = db.create_binder_item(ch_uuid, "Scene 1: Alone in the Woods", "Text")
        db.write_scene(sc3_uuid, text="Another scene with a conflicting title.", synopsis="", notes="")
        
        # Add a non-compile scene (should be excluded)
        ex_uuid = db.create_binder_item(ms_node.uuid, "Research Scene", "Text")
        
        def set_include_in_compile(nodes, uuid, val):
            for n in nodes:
                if n.uuid == uuid:
                    n.include_in_compile = val
                    return True
                if set_include_in_compile(n.children, uuid, val):
                    return True
            return False
            
        set_include_in_compile(db.get_outline(), ex_uuid, False)
        db.write_scene(ex_uuid, text="This should be ignored.", synopsis="", notes="")
        
        # 3. Call render_tool
        from mcp_server.server import render_tool
        output_file = os.path.join(self.temp_dir, "novel.md")
        res = render_tool(project_path, output_file, format="markdown")
        
        self.assertNotIn("isError", res)
        self.assertTrue(os.path.exists(output_file))
        
        # 4. Check the contents of the generated markdown file
        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Verify metadata title & author
        self.assertIn("# MyFantasyNovel", content)
        self.assertIn("**By Unknown Author**", content)
        
        # Verify Table of Contents
        self.assertIn("# Table of Contents", content)
        self.assertIn("- [Chapter One: The Awakening](#chapter-one-the-awakening)", content)
        self.assertIn("  - [Scene 1: Alone in the Woods](#scene-1-alone-in-the-woods)", content)
        self.assertIn("  - [Scene 2: Over the Hill](#scene-2-over-the-hill)", content)
        # Check duplicate title slug handling (should suffix)
        self.assertIn("  - [Scene 1: Alone in the Woods](#scene-1-alone-in-the-woods-1)", content)
        
        # Verify non-compile scene is excluded
        self.assertNotIn("Research Scene", content)
        self.assertNotIn("This should be ignored", content)
        
        # Verify generated headings vs extracted headings in body
        # Scene 1 (no heading) should have a generated heading '## Scene 1: Alone in the Woods'
        self.assertIn("## Scene 1: Alone in the Woods\n\n*It was dark in the woods.* He stood up.", content)
        
        # Scene 2 (has heading) should NOT get a duplicate generated heading and keep the file heading
        self.assertIn("# Scene 2: Over the Hill\n\nSome other text here.", content)
        # Should not have a double heading like '## Scene 2: Unnamed Originally'
        self.assertNotIn("## Scene 2: Unnamed Originally", content)
        
        # Scene 3 (conflicting title) should have a generated heading '## Scene 1: Alone in the Woods'
        self.assertIn("## Scene 1: Alone in the Woods\n\nAnother scene with a conflicting title.", content)

    def test_update_metadata_table_in_notes(self):
        from mcp_server.renderer import update_metadata_table_in_notes
        
        # Test 1: Empty notes
        res1 = update_metadata_table_in_notes("", "Cover", "Notes/cover.jpg")
        self.assertIn("### Agent Metadata", res1)
        self.assertIn("| Cover | Notes/cover.jpg |", res1)
        
        # Test 2: Notes with existing table without Cover
        notes2 = "### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| Title | My Book |\n| Author | Jane |"
        res2 = update_metadata_table_in_notes(notes2, "Cover", "Notes/cover.jpg")
        self.assertIn("| Cover | Notes/cover.jpg |", res2)
        self.assertIn("| Title | My Book |", res2)
        
        # Test 3: Notes with existing table with Cover (update)
        notes3 = "### Agent Metadata\n| Attribute | Value |\n| --- | --- |\n| Title | My Book |\n| Cover | old_cover.png |\n| Author | Jane |"
        res3 = update_metadata_table_in_notes(notes3, "Cover", "Notes/cover.jpg")
        self.assertIn("| Cover | Notes/cover.jpg |", res3)
        self.assertNotIn("old_cover.png", res3)
        self.assertIn("| Title | My Book |", res3)

    def test_render_tool_pdf(self):
        # 1. Create a mock book using FakeBookDb
        db = FakeBookDb.create_new(self.temp_dir, "MyPrintNovel")
        project_path = db.project_path
        
        # Initialize agent workspace so Prompt Directives exists
        db.create_agent_workspace()
        
        # 2. Add some scenes to Manuscript
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.type == "DraftFolder")
        ch_uuid = db.create_binder_item(ms_node.uuid, "Chapter One", "Folder")
        sc_uuid = db.create_binder_item(ch_uuid, "Scene 1", "Text")
        db.write_scene(sc_uuid, text="This is the story of Achilles. It has some justified paragraphs.", synopsis="", notes="")
        
        # 3. Call render_tool with PDF format and parameters
        from mcp_server.server import render_tool
        output_file = os.path.join(self.temp_dir, "novel.pdf")
        
        res = render_tool(
            project_path=project_path,
            output_path=output_file,
            format="pdf",
            trim_width=5.5,
            trim_height=8.5,
            bleed=True,
            gutter=0.5,
            outside_margin=0.4
        )
        
        self.assertNotIn("isError", res)
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(os.path.getsize(output_file), 0)
        
        # Verify PDF magic bytes
        with open(output_file, "rb") as f:
            magic = f.read(4)
            self.assertEqual(magic, b"%PDF")
            
        # Verify that print settings were saved to default project metadata in Prompt Directives notes
        agent_workspace = next(node for node in db.get_outline() if "[agent workspace]" in node.title.lower())
        pd_node = next(child for child in agent_workspace.children if child.title.lower() == "prompt directives")
        pd_data = db.read_scene(pd_node.uuid)
        
        self.assertIn("Trim Width", pd_data.notes)
        self.assertIn("5.5 in", pd_data.notes)
        self.assertIn("Trim Height", pd_data.notes)
        self.assertIn("8.5 in", pd_data.notes)
        self.assertIn("Bleed", pd_data.notes)
        self.assertIn("Yes", pd_data.notes)
        self.assertIn("Gutter", pd_data.notes)
        self.assertIn("0.5 in", pd_data.notes)
        self.assertIn("Outside Margin", pd_data.notes)
        self.assertIn("0.4 in", pd_data.notes)


    def test_pdf_alternating_templates_and_dynamic_margins(self):
        from unittest.mock import patch

        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import BaseDocTemplate

        # 1. Create a mock book database
        db = FakeBookDb.create_new(self.temp_dir, "TemplateTestBook")
        db.create_agent_workspace()
        
        # Add multiple chapters/scenes to ensure multiple pages are rendered
        binder = db.get_outline()
        ms_node = next(n for n in binder if n.type == "DraftFolder")
        
        for i in range(1, 5):
            ch_uuid = db.create_binder_item(ms_node.uuid, f"Chapter {i}", "Folder")
            sc_uuid = db.create_binder_item(ch_uuid, f"Scene {i}", "Text")
            # Write enough text to force multiple pages
            db.write_scene(sc_uuid, text="This is page text. " * 300)

        # Output path
        output_file = os.path.join(self.temp_dir, "test_alternating.pdf")

        # Track template selection calls
        template_calls = []
        original_handle = BaseDocTemplate.handle_nextPageTemplate

        def mock_handle_nextPageTemplate(self_doc, name):
            print(f"TEST_MOCK_TEMPLATE_CALL: {name} page: {getattr(self_doc, 'page', 0)}")
            template_calls.append((getattr(self_doc, 'page', 0), name))
            original_handle(self_doc, name)

        # Track draw calls to verify Y coordinates
        draw_string_calls = []
        line_calls = []
        original_draw_string = Canvas.drawCentredString
        original_line = Canvas.line

        def mock_draw_centred_string(self_canvas, x, y, text):
            draw_string_calls.append((y, text))
            original_draw_string(self_canvas, x, y, text)

        def mock_line(self_canvas, x1, y1, x2, y2):
            line_calls.append(y1)
            original_line(self_canvas, x1, y1, x2, y2)

        with patch('reportlab.platypus.BaseDocTemplate.handle_nextPageTemplate', autospec=True, side_effect=mock_handle_nextPageTemplate), \
             patch('reportlab.pdfgen.canvas.Canvas.drawCentredString', autospec=True, side_effect=mock_draw_centred_string), \
             patch('reportlab.pdfgen.canvas.Canvas.line', autospec=True, side_effect=mock_line):
             
             from mcp_server.server import render_tool
             render_tool(
                 project_path=db.project_path,
                 output_path=output_file,
                 format="pdf",
                 trim_width=6.0,
                 trim_height=9.0,
                 bleed=False,
                 gutter=0.5,
                 outside_margin=0.4,
                 top_margin=0.75,
                 bottom_margin=0.8
             )

        # 2. Assert template alternation:
        # page 1 starts: self.page is 0 -> next_template = "Even" (for page 2)
        # page 2 starts: self.page is 1 -> next_template = "Odd" (for page 3)
        # page 3 starts: self.page is 2 -> next_template = "Even" (for page 4)
        self.assertGreater(len(template_calls), 2)
        
        # Verify page 1 starting (self.page == 0) sets next template to "Even"
        p0_calls = [name for p, name in template_calls if p == 0]
        self.assertIn("Even", p0_calls)
        
        # Verify page 2 starting (self.page == 1) sets next template to "Odd"
        p1_calls = [name for p, name in template_calls if p == 1]
        self.assertIn("Odd", p1_calls)
        
        # Verify page 3 starting (self.page == 2) sets next template to "Even"
        p2_calls = [name for p, name in template_calls if p == 2]
        self.assertIn("Even", p2_calls)

        # 3. Assert dynamic header/footer coordinates
        # pt_trim_h = 9.0 * 72 = 648
        # pt_top = 0.75 * 72 = 54
        # pt_bottom = 0.8 * 72 = 57.6
        # Expected y_header = min(648 - 54 + 18, 648 - 32) = min(612, 616) = 612
        # Expected y_line = 612 - 8 = 604
        # Expected y_footer = max(57.6 - 18, 32) = max(39.6, 32) = 39.6
        
        header_ys = [y for y, text in draw_string_calls if text in ("TemplateTestBook", "Unknown Author")]
        footer_ys = [y for y, text in draw_string_calls if text.isdigit()]
        line_ys = line_calls
        
        self.assertTrue(len(header_ys) > 0)
        self.assertTrue(len(footer_ys) > 0)
        self.assertTrue(len(line_ys) > 0)
        
        self.assertTrue(all(abs(y - 612) < 0.1 for y in header_ys))
        self.assertTrue(all(abs(y - 39.6) < 0.1 for y in footer_ys))
        self.assertTrue(all(abs(y - 604) < 0.1 for y in line_ys))

class TestWatermarkRemovalTool(FakeDbTestCase):
    def test_remove_image_watermark_tool(self):
        from unittest.mock import MagicMock, patch

        # Create dummy source image
        from PIL import Image

        from mcp_server.server import remove_image_watermark_tool
        src_img_path = os.path.join(self.temp_dir, "test_watermarked.png")
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(src_img_path)

        target_img_path = os.path.join(self.temp_dir, "test_cleaned.png")

        # Mock the GeminiEngine.remove_watermark call
        mock_remove = MagicMock(side_effect=lambda img: img)

        with patch("remove_ai_watermarks.gemini_engine.GeminiEngine.remove_watermark", mock_remove):
            res = remove_image_watermark_tool(
                source_filename=src_img_path,
                target_filename=target_img_path
            )
            self.assertFalse(res.get("isError", False))
            self.assertIn("Successfully removed watermark", res["content"][0]["text"])
            mock_remove.assert_called_once()
            
            # Check that the target file was created
            self.assertTrue(os.path.exists(target_img_path))

    def test_remove_image_watermark_tool_missing_file(self):
        from mcp_server.server import remove_image_watermark_tool
        
        non_existent_path = os.path.join(self.temp_dir, "does_not_exist.png")
        target_img_path = os.path.join(self.temp_dir, "test_cleaned.png")

        res = remove_image_watermark_tool(
            source_filename=non_existent_path,
            target_filename=target_img_path
        )
        self.assertTrue(res.get("isError"))
        self.assertIn("does not exist", res["content"][0]["text"])

if __name__ == "__main__":
    unittest.main()

