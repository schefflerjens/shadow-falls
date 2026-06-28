import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from mcp_server.book_codex import (
    format_codex_context_block,
    match_entities,
    parse_codex,
)
from mcp_server.book_outline import compile_full_outline
from mcp_server.engine.scrivener_engine import (
    clone_project_structure,
    compile_manuscript,
    create_agent_workspace,
    create_new_project_folders,
    create_project_from_schema,
    create_scene_snapshot,
    delete_binder_item_element,
    find_scrivx_path,
    get_scene_files,
    insert_binder_item,
    parse_binder,
    patch_scene,
    save_scene_files,
    search_project,
    update_binder_item_meta,
)
from mcp_server.rtf_utils import rtf_to_markdown, text_to_rtf


class TestRTFUtils(unittest.TestCase):
    def test_text_to_rtf_ascii(self):
        text = "Hello World"
        rtf = text_to_rtf(text)
        self.assertIn("Hello World", rtf)
        self.assertTrue(rtf.startswith(r"{\rtf1"))
        
    def test_text_to_rtf_escapes(self):
        text = "Curly { braces } and backslash \\"
        rtf = text_to_rtf(text)
        self.assertIn("\\{", rtf)
        self.assertIn("\\}", rtf)
        self.assertIn("\\\\", rtf)
        
    def test_text_to_rtf_unicode(self):
        text = "Smiley 😊 and accented é character"
        rtf = text_to_rtf(text)
        # Check standard signed unicode representation in RTF
        self.assertIn("\\u-10179?", rtf) # 😊
        self.assertIn("\\u233?", rtf)     # é
        
    def test_text_to_rtf_line_endings(self):
        text = "Paragraph 1\r\nParagraph 2\rParagraph 3"
        rtf = text_to_rtf(text)
        self.assertIn("Paragraph 1\\par\nParagraph 2\\par\nParagraph 3", rtf)
        
    def test_rtf_to_markdown_basic(self):
        rtf = r"{\rtf1\ansi\deff0 This is \b bold\b0  text.}"
        text = rtf_to_markdown(rtf)
        self.assertEqual(text, "This is bold text.")

class TestScrivenerParser(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for project creation tests
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Cleanup temp directory
        shutil.rmtree(self.temp_dir)
        
    def test_create_new_book(self):
        project_path = create_new_project_folders(self.temp_dir, "MyMockNovel")
        self.assertTrue(os.path.isdir(project_path))
        self.assertTrue(project_path.endswith(".scriv"))
        
        # Verify default folder structure
        self.assertTrue(os.path.isdir(os.path.join(project_path, "Files", "Data")))
        self.assertTrue(os.path.isdir(os.path.join(project_path, "Settings")))
        self.assertTrue(os.path.isdir(os.path.join(project_path, "Snapshots")))
        
        # Verify scrivx exists and is valid XML
        scrivx_path = find_scrivx_path(project_path)
        self.assertTrue(os.path.isfile(scrivx_path))
        
        tree = ET.parse(scrivx_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "ScrivenerProject")
        
        # Parse binder
        outline = parse_binder(scrivx_path)
        self.assertEqual(len(outline), 6) # Manuscript, Characters, Places, Notes, Research, Trash
        titles = [item["title"] for item in outline]
        self.assertIn("Manuscript", titles)
        self.assertIn("Characters", titles)
        self.assertIn("Trash", titles)
        
    def test_insert_and_delete_binder_item(self):
        project_path = create_new_project_folders(self.temp_dir, "MyMockNovel")
        scrivx_path = find_scrivx_path(project_path)
        outline = parse_binder(scrivx_path)
        
        manuscript_uuid = outline[0]["uuid"]
        self.assertEqual(outline[0]["title"], "Manuscript")
        
        # Insert a new scene under Manuscript
        new_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Chapter 1 Intro", "Text")
        self.assertTrue(len(new_uuid) > 0)
        
        # Verify it's present in the outline
        updated_outline = parse_binder(scrivx_path)
        manuscript_item = updated_outline[0]
        self.assertEqual(len(manuscript_item["children"]), 1)
        self.assertEqual(manuscript_item["children"][0]["title"], "Chapter 1 Intro")
        self.assertEqual(manuscript_item["children"][0]["uuid"], new_uuid)
        
        # Save scene files
        text = "It was a dark and stormy night."
        notes = "Make it more atmospheric."
        synopsis = "Introduce the main character."
        save_scene_files(project_path, new_uuid, text, notes, synopsis)
        
        # Read back scene files
        scene_data = get_scene_files(project_path, new_uuid)
        self.assertEqual(scene_data["text"], text)
        self.assertEqual(scene_data["notes"], notes)
        self.assertEqual(scene_data["synopsis"], synopsis)
        
        # Rename scene
        update_binder_item_meta(scrivx_path, new_uuid, "Chapter 1 Revised")
        renamed_outline = parse_binder(scrivx_path)
        self.assertEqual(renamed_outline[0]["children"][0]["title"], "Chapter 1 Revised")
        
        # Soft delete (move to Trash)
        delete_binder_item_element(scrivx_path, new_uuid, soft_delete=True)
        deleted_outline = parse_binder(scrivx_path)
        self.assertEqual(len(deleted_outline[0]["children"]), 0) # Removed from manuscript
        
        # Check that it's in Trash
        trash_item = deleted_outline[5]
        self.assertEqual(trash_item["title"], "Trash")
        self.assertEqual(len(trash_item["children"]), 1)
        self.assertEqual(trash_item["children"][0]["uuid"], new_uuid)

    def test_clone_project_structure(self):
        # Create source project
        source_path = create_new_project_folders(self.temp_dir, "SourceNovel")
        source_scrivx = find_scrivx_path(source_path)
        
        # Insert a chapter and a scene in source project
        outline = parse_binder(source_scrivx)
        manuscript_uuid = outline[0]["uuid"]
        chapter_uuid = insert_binder_item(source_scrivx, manuscript_uuid, "Chapter 1", "Folder")
        scene_uuid = insert_binder_item(source_scrivx, chapter_uuid, "Scene 1", "Text")
        
        # Write scene story text and synopsis
        save_scene_files(source_path, scene_uuid, text="Original draft text.", notes="Writing note.", synopsis="Original beat synopsis.")
        
        # Clone structural outline
        target_path = clone_project_structure(source_path, self.temp_dir, "TargetNovel", copy_synopses=True)
        self.assertTrue(os.path.isdir(target_path))
        
        target_scrivx = find_scrivx_path(target_path)
        target_outline = parse_binder(target_scrivx)
        
        # Verify structure cloned
        self.assertEqual(target_outline[0]["title"], "Manuscript")
        self.assertEqual(len(target_outline[0]["children"]), 1)
        self.assertEqual(target_outline[0]["children"][0]["title"], "Chapter 1")
        self.assertEqual(target_outline[0]["children"][0]["type"], "Folder")
        
        cloned_chapter = target_outline[0]["children"][0]
        self.assertEqual(len(cloned_chapter["children"]), 1)
        self.assertEqual(cloned_chapter["children"][0]["title"], "Scene 1")
        self.assertEqual(cloned_chapter["children"][0]["type"], "Text")
        
        cloned_scene_uuid = cloned_chapter["children"][0]["uuid"]
        
        # Verify draft text was reset to empty, but synopsis and notes were copied
        cloned_data = get_scene_files(target_path, cloned_scene_uuid)
        self.assertEqual(cloned_data["text"], "")
        self.assertEqual(cloned_data["synopsis"], "Original beat synopsis.")
        self.assertEqual(cloned_data["notes"], "Writing note.")

    def test_create_project_from_schema(self):
        schema = [
            {
                "title": "Act I: Departure",
                "type": "Folder",
                "children": [
                    {
                        "title": "Beat 1: Opening Image",
                        "type": "Text",
                        "synopsis": "Establish status quo.",
                        "notes": "Tone should be warm."
                    },
                    {
                        "title": "Beat 2: Inciting Incident",
                        "type": "Text",
                        "synopsis": "Disrupt status quo."
                    }
                ]
            }
        ]
        
        project_path = create_project_from_schema(self.temp_dir, "SchemaNovel", schema)
        self.assertTrue(os.path.isdir(project_path))
        
        scrivx_path = find_scrivx_path(project_path)
        outline = parse_binder(scrivx_path)
        
        manuscript = outline[0]
        self.assertEqual(manuscript["title"], "Manuscript")
        self.assertEqual(len(manuscript["children"]), 1)
        
        act = manuscript["children"][0]
        self.assertEqual(act["title"], "Act I: Departure")
        self.assertEqual(act["type"], "Folder")
        self.assertEqual(len(act["children"]), 2)
        
        b1 = act["children"][0]
        self.assertEqual(b1["title"], "Beat 1: Opening Image")
        self.assertEqual(b1["type"], "Text")
        
        b2 = act["children"][1]
        self.assertEqual(b2["title"], "Beat 2: Inciting Incident")
        self.assertEqual(b2["type"], "Text")
        
        # Verify content
        b1_data = get_scene_files(project_path, b1["uuid"])
        self.assertEqual(b1_data["text"], "")
        self.assertEqual(b1_data["synopsis"], "Establish status quo.")
        self.assertEqual(b1_data["notes"], "Tone should be warm.")

    def test_create_agent_workspace(self):
        project_path = create_new_project_folders(self.temp_dir, "WorkspaceNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        # Create agent workspace
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        self.assertTrue(len(workspace_uuid) > 0)
        
        outline = parse_binder(scrivx_path)
        
        # Find workspace folder in outline
        workspace_item = None
        for item in outline:
            if item["uuid"] == workspace_uuid:
                workspace_item = item
                break
                
        self.assertIsNotNone(workspace_item)
        self.assertEqual(workspace_item["title"], "[Agent Workspace]")
        self.assertEqual(workspace_item["type"], "Folder")
        self.assertEqual(len(workspace_item["children"]), 4)
        
        child_titles = [child["title"] for child in workspace_item["children"]]
        self.assertIn("Prompt Directives", child_titles)
        self.assertIn("Session Memory", child_titles)
        self.assertIn("Task Checklist", child_titles)
        self.assertIn("Codex", child_titles)
        
        # Find Codex folder in workspace children
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        self.assertEqual(codex_item["type"], "Folder")
        self.assertEqual(len(codex_item["children"]), 3)
        
        codex_child_titles = [child["title"] for child in codex_item["children"]]
        self.assertIn("Characters", codex_child_titles)
        self.assertIn("Places", codex_child_titles)
        self.assertIn("Lore & Factions", codex_child_titles)
        
        # Verify Characters folder structure
        chars_item = [child for child in codex_item["children"] if child["title"] == "Characters"][0]
        self.assertEqual(chars_item["type"], "Folder")
        self.assertEqual(len(chars_item["children"]), 1)
        self.assertEqual(chars_item["children"][0]["title"], "Character Profile Template")
        self.assertEqual(chars_item["children"][0]["type"], "Text")
        
        # Verify content of Prompt Directives
        prompt_directives_item = [child for child in workspace_item["children"] if child["title"] == "Prompt Directives"][0]
        pd_data = get_scene_files(project_path, prompt_directives_item["uuid"])
        self.assertIn("Style Guide & Prompt Directives", pd_data["text"])
        self.assertIn("POV", pd_data["text"])
        
        # Verify notes of Character Profile Template
        char_tmpl_uuid = chars_item["children"][0]["uuid"]
        char_tmpl_data = get_scene_files(project_path, char_tmpl_uuid)
        self.assertIn("# Character Profile", char_tmpl_data["text"])
        self.assertIn("### Character Metadata", char_tmpl_data["notes"])
        self.assertIn("Timeline States", char_tmpl_data["notes"])

    def test_search_project(self):
        project_path = create_new_project_folders(self.temp_dir, "SearchNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        outline = parse_binder(scrivx_path)
        manuscript_uuid = outline[0]["uuid"]
        
        # Create a scene with text & synopsis
        scene_a = insert_binder_item(scrivx_path, manuscript_uuid, "Scene A", "Text")
        save_scene_files(project_path, scene_a, text="Achilles was a mighty warrior.", notes="", synopsis="The legendary tale of Achilles.")
        
        # Create another scene with matching notes
        scene_b = insert_binder_item(scrivx_path, manuscript_uuid, "Scene B", "Text")
        save_scene_files(project_path, scene_b, text="Other text.", notes="A detail about the Trojan War.", synopsis="")
        
        # Search for 'Achilles'
        res_a = search_project(project_path, "Achilles")
        self.assertEqual(len(res_a), 1)
        self.assertEqual(res_a[0]["title"], "Scene A")
        self.assertIn("text", res_a[0]["matches"])
        self.assertIn("synopsis", res_a[0]["matches"])
        self.assertIn("Achilles", res_a[0]["matches"]["text"]["snippet"])
        
        # Search for 'Trojan'
        res_b = search_project(project_path, "Trojan")
        self.assertEqual(len(res_b), 1)
        self.assertEqual(res_b[0]["title"], "Scene B")
        self.assertIn("notes", res_b[0]["matches"])
        self.assertNotIn("text", res_b[0]["matches"])

    def test_compile_manuscript(self):
        project_path = create_new_project_folders(self.temp_dir, "CompileNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        outline = parse_binder(scrivx_path)
        manuscript_uuid = outline[0]["uuid"]
        
        # Insert a Chapter Folder and Scenes under it
        chapter_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Chapter 1", "Folder")
        scene_1_uuid = insert_binder_item(scrivx_path, chapter_uuid, "Scene 1.1", "Text")
        scene_2_uuid = insert_binder_item(scrivx_path, chapter_uuid, "Scene 1.2", "Text")
        
        save_scene_files(project_path, scene_1_uuid, text="First scene draft.")
        save_scene_files(project_path, scene_2_uuid, text="Second scene draft.")
        
        # Compile
        draft = compile_manuscript(project_path)
        
        self.assertIn("## Chapter 1", draft)
        self.assertIn("### Scene 1.1", draft)
        self.assertIn("First scene draft.", draft)
        self.assertIn("### Scene 1.2", draft)
        self.assertIn("Second scene draft.", draft)

    def test_patch_scene(self):
        project_path = create_new_project_folders(self.temp_dir, "PatchNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        outline = parse_binder(scrivx_path)
        manuscript_uuid = outline[0]["uuid"]
        
        scene_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Scene A", "Text")
        save_scene_files(project_path, scene_uuid, text="Achilles met Hector on the dusty plains.")
        
        # 1. Successful exact patch
        success = patch_scene(project_path, scene_uuid, "Hector", "Patroclus")
        self.assertTrue(success)
        
        scene_data = get_scene_files(project_path, scene_uuid)
        self.assertEqual(scene_data["text"], "Achilles met Patroclus on the dusty plains.")
        
        # 2. Successful ellipsis wildcard patch
        save_scene_files(project_path, scene_uuid, text="The quick brown fox jumps over the lazy dog.")
        success2 = patch_scene(project_path, scene_uuid, "quick...jumps", "slow red panda jumps")
        self.assertTrue(success2)
        
        scene_data = get_scene_files(project_path, scene_uuid)
        self.assertEqual(scene_data["text"], "The slow red panda jumps over the lazy dog.")
        
        # 3. Ellipsis wildcard patch: ambiguous (multiple matches)
        save_scene_files(project_path, scene_uuid, text="The quick brown fox jumps. Another quick brown fox jumps.")
        with self.assertRaises(ValueError) as ctx:
            patch_scene(project_path, scene_uuid, "quick...jumps", "something")
        self.assertIn("found 2 times in scene", str(ctx.exception))
        
        # 4. Failure: text not found, triggers fuzzy error suggestion
        save_scene_files(project_path, scene_uuid, text="She said, 'I know the feeling,' and looked away.")
        with self.assertRaises(ValueError) as ctx:
            patch_scene(project_path, scene_uuid, "'I know the feeling,' I said.", "something else")
        self.assertIn("Did you mean", str(ctx.exception))
        self.assertIn("similarity", str(ctx.exception))
        self.assertIn("'I know the feeling,' and looked away.", str(ctx.exception))
        
        # 5. Failure: ambiguous exact match (text appears twice)
        save_scene_files(project_path, scene_uuid, text="Hector met Hector near the gates.")
        with self.assertRaises(ValueError) as ctx:
            patch_scene(project_path, scene_uuid, "Hector", "Achilles")
        self.assertIn("found 2 times in scene", str(ctx.exception))

    def test_get_scene_readability_metrics(self):
        from mcp_server.server import get_scene_readability_metrics_tool
        project_path = create_new_project_folders(self.temp_dir, "MetricsNovel")
        scrivx_path = find_scrivx_path(project_path)
        outline = parse_binder(scrivx_path)
        manuscript_uuid = outline[0]["uuid"]
        
        scene_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Scene A", "Text")
        save_scene_files(project_path, scene_uuid, text="This is a simple scene. It has short sentences. The passive voice is not used here.")
        
        # Run tool
        res = get_scene_readability_metrics_tool(project_path, scene_uuid)
        self.assertNotIn("isError", res or {})
        
        metrics = json.loads(res["content"][0]["text"])
        self.assertEqual(metrics["status"], "success")
        self.assertIn("flesch_kincaid_grade", metrics)
        self.assertIn("passive_voice_density", metrics)
        self.assertIn("word_count", metrics)
        self.assertGreater(metrics["word_count"], 0)

class TestScrivenerCodex(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        
    def test_codex_parsing_and_temporal_overrides(self):
        project_path = create_new_project_folders(self.temp_dir, "CodexNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        # Initialize workspace
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        outline = parse_binder(scrivx_path)
        
        # Find Codex Characters folder
        workspace_item = [item for item in outline if item["uuid"] == workspace_uuid][0]
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        chars_folder = [child for child in codex_item["children"] if child["title"] == "Characters"][0]
        
        # Add a character "Jim" under Characters folder
        jim_uuid = insert_binder_item(scrivx_path, chars_folder["uuid"], "Jim", "Text")
        
        jim_text = "Jim is a blacksmith in the village."
        jim_notes = (
            "### Character Metadata\n"
            "| Attribute | Value |\n"
            "| --- | --- |\n"
            "| Full Name | James Miller |\n"
            "| Aliases | Jim, Jimmy |\n"
            "| Age | 42 |\n\n"
            "### Relationships\n"
            "| Target Entity (UUID or Name) | Relationship Type | Detail / Status |\n"
            "| --- | --- | --- |\n"
            "| Janet | Spouse | Married for 15 years |\n\n"
            "### Chronological Timeline States (Anti-Spoiler)\n"
            "| Act / Chapter | State Name | State Details & Overrides |\n"
            "| --- | --- | --- |\n"
            "| Act 1 | Friendly Blacksmith | Quiet neighbor, keeps to himself. |\n"
            "| Act 3 | Exposed Culprit | Revealed to be the serial poisoner. Cold and ruthless. |"
        )
        save_scene_files(project_path, jim_uuid, text=jim_text, notes=jim_notes, synopsis="A blacksmith.")
        
        # 1. Parse without act (base details)
        db_base = parse_codex(project_path)
        self.assertEqual(len(db_base["characters"]), 1)
        jim_entry = db_base["characters"][0]
        self.assertEqual(jim_entry["title"], "Jim")
        self.assertEqual(jim_entry["metadata"].get("full name"), "James Miller")
        self.assertEqual(jim_entry["metadata"].get("age"), "42")
        self.assertIn("Jim", jim_entry["aliases"])
        self.assertIn("Jimmy", jim_entry["aliases"])
        self.assertEqual(len(jim_entry["relationships"]), 1)
        self.assertEqual(jim_entry["relationships"][0]["target"], "Janet")
        self.assertEqual(jim_entry["relationships"][0]["type"], "Spouse")
        self.assertIsNone(jim_entry["active_override"])
        self.assertEqual(jim_entry["summary"], jim_text)
        
        # 2. Parse with Act 1
        db_act1 = parse_codex(project_path, current_act="Act 1")
        jim_act1 = db_act1["characters"][0]
        self.assertIsNotNone(jim_act1["active_override"])
        self.assertEqual(jim_act1["active_override"]["state"], "Friendly Blacksmith")
        self.assertIn("Quiet neighbor, keeps to himself.", jim_act1["summary"])
        
        # 3. Parse with Act 3
        db_act3 = parse_codex(project_path, current_act="Act 3")
        jim_act3 = db_act3["characters"][0]
        self.assertIsNotNone(jim_act3["active_override"])
        self.assertEqual(jim_act3["active_override"]["state"], "Exposed Culprit")
        self.assertIn("Revealed to be the serial poisoner.", jim_act3["summary"])
        
    def test_location_containment_and_nested_paths(self):
        project_path = create_new_project_folders(self.temp_dir, "LocationNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        # Initialize workspace
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        outline = parse_binder(scrivx_path)
        
        # Find Codex Places folder
        workspace_item = [item for item in outline if item["uuid"] == workspace_uuid][0]
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        places_folder = [child for child in codex_item["children"] if child["title"] == "Places"][0]
        
        # Create nested folders: Shadow Falls > City Hall > Library
        shadow_falls_uuid = insert_binder_item(scrivx_path, places_folder["uuid"], "Shadow Falls", "Folder")
        city_hall_uuid = insert_binder_item(scrivx_path, shadow_falls_uuid, "City Hall", "Folder")
        library_uuid = insert_binder_item(scrivx_path, city_hall_uuid, "Library", "Text")
        
        save_scene_files(project_path, library_uuid, text="Dusty bookshelves.", notes="", synopsis="The town archive.")
        
        # Parse Codex
        db = parse_codex(project_path)
        self.assertEqual(len(db["places"]), 1)
        library_entry = db["places"][0]
        self.assertEqual(library_entry["title"], "Library")
        # Verify location path inheritance (excluding Codex and Places root nodes)
        self.assertEqual(library_entry["location_path"], ["Shadow Falls", "City Hall"])
        
    def test_entity_matching_and_context_block(self):
        project_path = create_new_project_folders(self.temp_dir, "MatchNovel")
        scrivx_path = find_scrivx_path(project_path)
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        outline = parse_binder(scrivx_path)
        
        workspace_item = [item for item in outline if item["uuid"] == workspace_uuid][0]
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        chars_folder = [child for child in codex_item["children"] if child["title"] == "Characters"][0]
        places_folder = [child for child in codex_item["children"] if child["title"] == "Places"][0]
        
        # Create Character Jim
        jim_uuid = insert_binder_item(scrivx_path, chars_folder["uuid"], "Jim", "Text")
        save_scene_files(project_path, jim_uuid, text="Jim the Blacksmith", notes="### Character Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Jimmy |", synopsis="")
        
        # Create Place Library
        lib_uuid = insert_binder_item(scrivx_path, places_folder["uuid"], "Library", "Text")
        save_scene_files(project_path, lib_uuid, text="A library room", notes="### Location Metadata\n| Attribute | Value |\n| --- | --- |\n| Aliases | Archive, Reading Room |", synopsis="")
        
        # Parse Codex database
        db = parse_codex(project_path)
        
        # Test exact name match
        matches1 = match_entities("Jim walked into the room.", db)
        self.assertEqual(len(matches1), 1)
        self.assertEqual(matches1[0]["title"], "Jim")
        
        # Test alias match (Jimmy)
        matches2 = match_entities("Jimmy was working hard.", db)
        self.assertEqual(len(matches2), 1)
        self.assertEqual(matches2[0]["title"], "Jim")
        
        # Test word boundaries (no substring match like 'Jimmy' in 'Jimmying')
        matches_sub = match_entities("He was jimmying the lock.", db)
        self.assertEqual(len(matches_sub), 0)
        
        # Test place alias match (Reading Room)
        matches3 = match_entities("The book was inside the Reading Room.", db)
        self.assertEqual(len(matches3), 1)
        self.assertEqual(matches3[0]["title"], "Library")
        
        # Test context block formatting
        context = format_codex_context_block([db["characters"][0], db["places"][0]])
        self.assertIn("## Active Lore & Codex References", context)
        self.assertIn("Characters", context)
        self.assertIn("Places", context)
        self.assertIn("Jim", context)
        self.assertIn("Library", context)

    def test_create_scene_snapshot(self):
        project_path = create_new_project_folders(self.temp_dir, "SnapshotNovel")
        scrivx_path = find_scrivx_path(project_path)
        
        outline = parse_binder(scrivx_path)
        manuscript_uuid = outline[0]["uuid"]
        
        scene_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Scene A", "Text")
        initial_text = "Initial draft text."
        save_scene_files(project_path, scene_uuid, text=initial_text, notes="", synopsis="")
        
        # 1. Take snapshot
        success = create_scene_snapshot(project_path, scene_uuid, "Version 1.0 Draft")
        self.assertTrue(success)
        
        # Verify index.xml exists and is correct
        scene_snapshots_dir = os.path.join(project_path, "Snapshots", f"{scene_uuid}.snapshots")
        index_xml_path = os.path.join(scene_snapshots_dir, "index.xml")
        self.assertTrue(os.path.exists(index_xml_path))
        
        tree = ET.parse(index_xml_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "Snapshots")
        self.assertEqual(len(root.findall("Snapshot")), 1)
        
        snapshot_node = root.find("Snapshot")
        self.assertEqual(snapshot_node.find("Title").text, "Version 1.0 Draft")
        date_str = snapshot_node.find("Date").text
        snapshot_id = date_str.replace(" ", "-").replace(":", "-")
        self.assertTrue(len(snapshot_id) > 0)
        
        # Verify snapshot RTF file exists and contains initial text
        snapshot_rtf_path = os.path.join(scene_snapshots_dir, f"{snapshot_id}.rtf")
        self.assertTrue(os.path.exists(snapshot_rtf_path))
        
        # Read back snapshot using RTF converter
        with open(snapshot_rtf_path, "r", encoding="utf-8") as f:
            snapshot_rtf_data = f.read()
        self.assertEqual(rtf_to_markdown(snapshot_rtf_data), initial_text)
        
        # 2. Modify active scene draft text and assert snapshot is isolated
        updated_text = "New edited text."
        save_scene_files(project_path, scene_uuid, text=updated_text)
        
        # Active file is updated
        active_data = get_scene_files(project_path, scene_uuid)
        self.assertEqual(active_data["text"], updated_text)
        
        # Snapshot file remains initial text
        with open(snapshot_rtf_path, "r", encoding="utf-8") as f:
            snapshot_rtf_data_2 = f.read()
        self.assertEqual(rtf_to_markdown(snapshot_rtf_data_2), initial_text)

    def test_prompt_assembler_compilation(self):
        from mcp_server.prompt_assembler import compile_writing_prompt
        project_path = create_new_project_folders(self.temp_dir, "AssemblerNovel")
        scrivx_path = find_scrivx_path(project_path)
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        outline = parse_binder(scrivx_path)
        
        manuscript_uuid = outline[0]["uuid"]
        
        # Insert two scenes
        scene_1_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Scene 1", "Text")
        save_scene_files(project_path, scene_1_uuid, text="Once upon a time in Shadow Falls.", notes="", synopsis="Start of the book.")
        
        scene_2_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Scene 2", "Text")
        save_scene_files(project_path, scene_2_uuid, text="", notes="", synopsis="Jim visits the library.")
        
        # Add Codex entries in workspace
        workspace_item = [item for item in outline if item["uuid"] == workspace_uuid][0]
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        chars_folder = [child for child in codex_item["children"] if child["title"] == "Characters"][0]
        places_folder = [child for child in codex_item["children"] if child["title"] == "Places"][0]
        
        jim_uuid = insert_binder_item(scrivx_path, chars_folder["uuid"], "Jim", "Text")
        save_scene_files(project_path, jim_uuid, text="James the blacksmith.", notes="### Character Metadata\n| Attribute | Value |\n| Aliases | Jimmy |", synopsis="")
        
        lib_uuid = insert_binder_item(scrivx_path, places_folder["uuid"], "Library", "Text")
        save_scene_files(project_path, lib_uuid, text="Dusty town archive.", notes="### Location Metadata\n| Attribute | Value |\n| Aliases | Archive, Reading Room |", synopsis="")
        
        # Compile prompt for scene 2
        payload = compile_writing_prompt(project_path, scene_2_uuid, current_act="Act 1")
        self.assertIn("system_prompt", payload)
        self.assertIn("user_prompt", payload)
        
        user_prompt = payload["user_prompt"]
        self.assertIn("Once upon a time in Shadow Falls.", user_prompt) # Continuity
        self.assertIn("Jim visits the library.", user_prompt) # Active Beats
        self.assertIn("James the blacksmith.", user_prompt) # Matched Character Lore
        self.assertIn("Dusty town archive.", user_prompt) # Matched Location Lore
        self.assertIn(lib_uuid, payload["matched_entries_uuids"]) # Library UUID matched
        self.assertIn(jim_uuid, payload["matched_entries_uuids"]) # Jim UUID matched

    def test_compile_full_outline_and_character_tracking(self):
        project_path = create_new_project_folders(self.temp_dir, "OutlineNovel")
        scrivx_path = find_scrivx_path(project_path)
        workspace_uuid = create_agent_workspace(project_path, "[Agent Workspace]")
        outline = parse_binder(scrivx_path)
        
        manuscript_uuid = outline[0]["uuid"]
        
        # Add Codex Character Jane & Place Library
        workspace_item = [item for item in outline if item["uuid"] == workspace_uuid][0]
        codex_item = [child for child in workspace_item["children"] if child["title"] == "Codex"][0]
        chars_folder = [child for child in codex_item["children"] if child["title"] == "Characters"][0]
        places_folder = [child for child in codex_item["children"] if child["title"] == "Places"][0]
        
        jane_uuid = insert_binder_item(scrivx_path, chars_folder["uuid"], "Jane", "Text")
        save_scene_files(project_path, jane_uuid, text="Jane is the hero.", notes="### Character Metadata\n| Attribute | Value |\n| Aliases | Janet |", synopsis="")
        
        lib_uuid = insert_binder_item(scrivx_path, places_folder["uuid"], "Library", "Text")
        save_scene_files(project_path, lib_uuid, text="Dusty town archive.", notes="### Location Metadata\n| Attribute | Value |\n| Aliases | Archive |", synopsis="")
        
        # Create Manuscript structural outline
        chapter_uuid = insert_binder_item(scrivx_path, manuscript_uuid, "Chapter 1", "Folder")
        save_scene_files(project_path, chapter_uuid, text="", notes="", synopsis="Jane arrives at the town harbor.")
        
        scene_uuid = insert_binder_item(scrivx_path, chapter_uuid, "Scene 1.1", "Text")
        save_scene_files(project_path, scene_uuid, text="", notes="", synopsis="Jane searches the library archive.")
        
        # Compile
        codex_db = parse_codex(project_path)
        outline_payload = compile_full_outline(project_path, codex_db)
        
        flat_list = outline_payload["flat_list"]
        markdown = outline_payload["markdown"]
        
        # Verify Flat List structure
        self.assertEqual(len(flat_list), 3) # Manuscript root, Chapter 1, Scene 1.1
        
        chap_item = [f for f in flat_list if f["title"] == "Chapter 1"][0]
        self.assertEqual(chap_item["type"], "Folder")
        self.assertIn("Jane", chap_item["characters"])
        
        scene_item = [f for f in flat_list if f["title"] == "Scene 1.1"][0]
        self.assertEqual(scene_item["type"], "Text")
        self.assertIn("Jane", scene_item["characters"])
        self.assertIn("Library", scene_item["places"]) # Matches 'library' and 'archive'
        
        # Verify Markdown compiled output
        self.assertIn("Chapter: Chapter 1", markdown)
        self.assertIn("Scene: Scene 1.1", markdown)
        self.assertIn("Characters:** Jane", markdown)
        self.assertIn("Places:** Library", markdown)

if __name__ == "__main__":
    unittest.main()
