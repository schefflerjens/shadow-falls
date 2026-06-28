import os
import shutil
import subprocess
import tempfile
import unittest

from mcp_server.engine.book_engine import (
    DOC_PROMPT_DIRECTIVES,
    DOC_SESSION_MEMORY,
    DOC_TASK_CHECKLIST,
    FOLDER_AGENT_WORKSPACE,
    FOLDER_CHARACTERS,
    FOLDER_CODEX,
    FOLDER_MANUSCRIPT,
    FOLDER_NOTES,
    FOLDER_PLACES,
    FOLDER_RESEARCH,
    FOLDER_TRASH,
    TYPE_DRAFT_FOLDER,
    TYPE_FOLDER,
    TYPE_RESEARCH_FOLDER,
    TYPE_TEXT,
    TYPE_TRASH_FOLDER,
    get_book_db,
)
from mcp_server.engine.gitbook_engine import GitBookDb


class TestGitBookDb(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory that will act as the Git repository root
        self.temp_dir = tempfile.mkdtemp()
        # Initialize Git in the temp directory
        subprocess.run(["git", "init"], cwd=self.temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        # Configure Git user identity for test commits to succeed
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        # Create an initial commit so that HEAD exists
        dummy_file = os.path.join(self.temp_dir, "init.txt")
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write("init")
        subprocess.run(["git", "add", "init.txt"], cwd=self.temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_routing_and_unsupported_format(self):
        # Confirm that get_book_db correctly instantiates GitBookDb for paths ending with .gitbook
        db_path = os.path.join(self.temp_dir, "MyNovel.gitbook")
        # Pre-create the directory so we can instantiate
        os.makedirs(db_path, exist_ok=True)
        os.makedirs(os.path.join(db_path, "Manuscript"), exist_ok=True)
        with open(os.path.join(db_path, "binder.json"), "w") as f:
            f.write("[]")

        db = get_book_db(db_path)
        self.assertIsInstance(db, GitBookDb)

        # Confirm value error for unsupported format
        with self.assertRaises(ValueError):
            get_book_db(os.path.join(self.temp_dir, "MyNovel.invalid"))

    def test_outside_git_repo_fails(self):
        # Create a temp directory not in any Git repository
        non_git_dir = tempfile.mkdtemp()
        try:
            # Attempt to instantiate GitBookDb there should raise RuntimeError
            # (Note that we must create binder.json first or mock it, but calling create_new is easier)
            with self.assertRaises(RuntimeError):
                GitBookDb.create_new(non_git_dir, "NoGitProj.gitbook")
        finally:
            shutil.rmtree(non_git_dir)

    def test_create_new_book(self):
        db = GitBookDb.create_new(self.temp_dir, "MyNovel")
        project_path = db.project_path
        self.assertTrue(os.path.isdir(project_path))
        self.assertTrue(project_path.endswith(".gitbook"))
        self.assertTrue(os.path.isdir(os.path.join(project_path, "Manuscript")))
        self.assertTrue(os.path.isfile(os.path.join(project_path, "binder.json")))

        outline = db.get_outline()
        self.assertEqual(len(outline), 6)
        titles = [node.title for node in outline]
        self.assertEqual(titles, [
            FOLDER_MANUSCRIPT, FOLDER_CHARACTERS, FOLDER_PLACES,
            FOLDER_NOTES, FOLDER_RESEARCH, FOLDER_TRASH
        ])
        
        # Verify node types match expectations
        self.assertEqual(outline[0].type, TYPE_DRAFT_FOLDER)
        self.assertEqual(outline[1].type, TYPE_FOLDER)
        self.assertEqual(outline[4].type, TYPE_RESEARCH_FOLDER)
        self.assertEqual(outline[5].type, TYPE_TRASH_FOLDER)

    def test_insert_update_and_delete_binder_item(self):
        db = GitBookDb.create_new(self.temp_dir, "MyNovel")
        outline = db.get_outline()
        manuscript_uuid = outline[0].uuid

        # Insert a scene
        scene_uuid = db.create_binder_item(manuscript_uuid, "Intro Scene", TYPE_TEXT)
        self.assertIsNotNone(scene_uuid)

        # Verify added to outline
        updated_outline = db.get_outline()
        self.assertEqual(len(updated_outline[0].children), 1)
        self.assertEqual(updated_outline[0].children[0].title, "Intro Scene")
        self.assertEqual(updated_outline[0].children[0].uuid, scene_uuid)

        # Write text and read it back
        db.write_scene(scene_uuid, text="Hello prose.", notes="My editorial notes.", synopsis="Intro character.")
        scene_files = db.read_scene(scene_uuid)
        self.assertEqual(scene_files.text, "Hello prose.")
        self.assertEqual(scene_files.notes, "My editorial notes.")
        self.assertEqual(scene_files.synopsis, "Intro character.")

        # Update metadata (rename)
        success = db.update_binder_item_meta(scene_uuid, title="Intro Scene Revised")
        self.assertTrue(success)
        scene_uuid = "Manuscript/Intro Scene Revised"
        self.assertEqual(db.get_outline()[0].children[0].title, "Intro Scene Revised")

        # Soft Delete (moves to trash)
        success = db.delete_binder_item(scene_uuid, soft_delete=True)
        self.assertTrue(success)
        scene_uuid = "Trash/Intro Scene Revised"
        self.assertEqual(len(db.get_outline()[0].children), 0)
        
        trash_node = db.get_outline()[5]
        self.assertEqual(trash_node.title, FOLDER_TRASH)
        self.assertEqual(len(trash_node.children), 1)
        self.assertEqual(trash_node.children[0].uuid, scene_uuid)

        # Hard Delete (permanently delete from trash)
        success = db.delete_binder_item(scene_uuid, soft_delete=False)
        self.assertTrue(success)
        self.assertEqual(len(trash_node.children), 0)

        # Ensure raw files are deleted on hard delete
        prose_path = os.path.join(db.project_path, "Trash", "Intro Scene Revised.md")
        self.assertFalse(os.path.exists(prose_path))

    def test_clone_structure(self):
        source_db = GitBookDb.create_new(self.temp_dir, "SourceBook")
        outline = source_db.get_outline()
        ms_uuid = outline[0].uuid
        scene_uuid = source_db.create_binder_item(ms_uuid, "Scene 1", TYPE_TEXT)
        source_db.write_scene(scene_uuid, text="Source prose", notes="Source notes", synopsis="Source synopsis")

        # Clone
        target_db = GitBookDb.clone_structure(source_db, self.temp_dir, "ClonedBook", copy_synopses=True)
        self.assertEqual(target_db.get_outline()[0].children[0].title, "Scene 1")
        
        cloned_scene = target_db.read_scene(scene_uuid)
        self.assertEqual(cloned_scene.text, "") # Draft text should be cleared
        self.assertEqual(cloned_scene.notes, "Source notes") # Notes should be copied
        self.assertEqual(cloned_scene.synopsis, "Source synopsis") # Synopsis should be copied since copy_synopses=True

        # Clone without synopses
        target_db_no_syn = GitBookDb.clone_structure(source_db, self.temp_dir, "ClonedBookNoSyn", copy_synopses=False)
        cloned_scene_no_syn = target_db_no_syn.read_scene(scene_uuid)
        self.assertEqual(cloned_scene_no_syn.synopsis, "")

    def test_create_from_schema(self):
        schema = [
            {
                "title": "Act I",
                "type": TYPE_FOLDER,
                "children": [
                    {
                        "title": "Scene 1.1",
                        "type": TYPE_TEXT,
                        "text": "Prose 1.1",
                        "notes": "Notes 1.1",
                        "synopsis": "Syn 1.1"
                    }
                ]
            }
        ]
        db = GitBookDb.create_from_schema(self.temp_dir, "SchemaNovel", schema)
        ms_node = db.get_outline()[0]
        self.assertEqual(len(ms_node.children), 1)
        self.assertEqual(ms_node.children[0].title, "Act I")
        self.assertEqual(ms_node.children[0].type, TYPE_FOLDER)

        scene_node = ms_node.children[0].children[0]
        self.assertEqual(scene_node.title, "Scene 1.1")
        self.assertEqual(scene_node.type, TYPE_TEXT)

        sf = db.read_scene(scene_node.uuid)
        self.assertEqual(sf.text, "Prose 1.1")
        self.assertEqual(sf.notes, "Notes 1.1")
        self.assertEqual(sf.synopsis, "Syn 1.1")

    def test_create_agent_workspace(self):
        db = GitBookDb.create_new(self.temp_dir, "WorkspaceBook")
        ws_uuid = db.create_agent_workspace()
        self.assertIsNotNone(ws_uuid)

        outline = db.get_outline()
        ws_node = next(n for n in outline if n.uuid == ws_uuid)
        self.assertEqual(ws_node.title, FOLDER_AGENT_WORKSPACE)

        titles = [c.title for c in ws_node.children]
        self.assertIn(DOC_PROMPT_DIRECTIVES, titles)
        self.assertIn(DOC_SESSION_MEMORY, titles)
        self.assertIn(DOC_TASK_CHECKLIST, titles)
        self.assertIn(FOLDER_CODEX, titles)

        # Check prompt directives content exists and is not empty
        pd_node = next(c for c in ws_node.children if c.title == DOC_PROMPT_DIRECTIVES)
        sf = db.read_scene(pd_node.uuid)
        self.assertGreater(len(sf.text), 0)

    def test_search_project(self):
        db = GitBookDb.create_new(self.temp_dir, "SearchBook")
        ms_uuid = db.get_outline()[0].uuid
        sc1 = db.create_binder_item(ms_uuid, "Scene One", TYPE_TEXT)
        sc2 = db.create_binder_item(ms_uuid, "Scene Two", TYPE_TEXT)

        db.write_scene(sc1, text="The mysterious knight rode into the castle.", notes="", synopsis="")
        db.write_scene(sc2, text="Inside, the princess waited.", notes="Mentions the mysterious knight.", synopsis="Waiting.")

        results = db.search_project("mysterious knight")
        self.assertEqual(len(results), 2)
        uuids = [r["uuid"] for r in results]
        self.assertIn(sc1, uuids)
        self.assertIn(sc2, uuids)

        # Check snippet match location
        sc2_res = next(r for r in results if r["uuid"] == sc2)
        self.assertIn("notes", sc2_res["matches"])
        self.assertEqual(sc2_res["matches"]["notes"]["count"], 1)

    def test_compile_manuscript(self):
        db = GitBookDb.create_new(self.temp_dir, "CompileBook")
        ms_uuid = db.get_outline()[0].uuid
        ch1 = db.create_binder_item(ms_uuid, "Chapter One", TYPE_FOLDER)
        sc1 = db.create_binder_item(ch1, "Scene A", TYPE_TEXT)
        sc2 = db.create_binder_item(ch1, "Scene B", TYPE_TEXT)

        db.write_scene(sc1, text="First paragraph.", notes="", synopsis="")
        db.write_scene(sc2, text="Second paragraph.", notes="", synopsis="")

        # Compile
        compiled = db.compile_manuscript()
        self.assertIn("## Chapter One", compiled)
        self.assertIn("#### Scene A", compiled)
        self.assertIn("First paragraph.", compiled)
        self.assertIn("#### Scene B", compiled)
        self.assertIn("Second paragraph.", compiled)

    def test_patch_scene_methods(self):
        db = GitBookDb.create_new(self.temp_dir, "PatchBook")
        ms_uuid = db.get_outline()[0].uuid
        scene_uuid = db.create_binder_item(ms_uuid, "Scene", TYPE_TEXT)
        db.write_scene(scene_uuid, text="Original text with apples and oranges.", notes="", synopsis="")

        # 1. patch_scene
        success = db.patch_scene(scene_uuid, "apples", "bananas")
        self.assertTrue(success)
        self.assertEqual(db.read_scene(scene_uuid).text, "Original text with bananas and oranges.")

        # test ambiguity
        db.write_scene(scene_uuid, text="abc abc")
        with self.assertRaises(ValueError):
            db.patch_scene(scene_uuid, "abc", "xyz")

        # test wildcard match
        db.write_scene(scene_uuid, text="Start middle end")
        success = db.patch_scene(scene_uuid, "Start...end", "Start replaced end")
        self.assertTrue(success)
        self.assertEqual(db.read_scene(scene_uuid).text, "Start replaced end")

        # 2. bulk_patch_scenes
        db.write_scene(scene_uuid, text="Red car, blue car")
        details = db.bulk_patch_scenes("car", "bike", [scene_uuid], dry_run=True)
        self.assertEqual(details[0]["matches_found"], 2)
        self.assertEqual(db.read_scene(scene_uuid).text, "Red car, blue car")  # Unchanged on dry run

        details = db.bulk_patch_scenes("car", "bike", [scene_uuid], dry_run=False)
        self.assertEqual(details[0]["matches_found"], 2)
        self.assertEqual(db.read_scene(scene_uuid).text, "Red bike, blue bike")

        # 3. regex_patch_scenes
        details = db.regex_patch_scenes(r"blue (\w+)", r"green \1", [scene_uuid])
        self.assertEqual(details[0]["matches_found"], 1)
        self.assertEqual(db.read_scene(scene_uuid).text, "Red bike, green bike")

        # 4. apply_patchset
        patches = [
            {"type": "exact", "target": "Red", "replacement": "Yellow"},
            {"type": "regex", "pattern": r"green (\w+)", "replacement": r"purple \1"}
        ]
        patch_results = db.apply_patchset(patches, [scene_uuid])
        self.assertEqual(len(patch_results), 2)
        self.assertEqual(db.read_scene(scene_uuid).text, "Yellow bike, purple bike")

    def test_git_snapshotting_and_reversion(self):
        db = GitBookDb.create_new(self.temp_dir, "GitBook")
        ms_uuid = db.get_outline()[0].uuid
        scene_uuid = db.create_binder_item(ms_uuid, "Scene", TYPE_TEXT)

        # Write initial version
        db.write_scene(scene_uuid, text="Version 1", notes="Notes 1", synopsis="Syn 1")
        # Create Snapshot 1
        success = db.create_scene_snapshot(scene_uuid, "First Snapshot")
        self.assertTrue(success)

        # Write version 2
        db.write_scene(scene_uuid, text="Version 2", notes="Notes 2", synopsis="Syn 2")
        # Create Snapshot 2
        success = db.create_scene_snapshot(scene_uuid, "Second Snapshot")
        self.assertTrue(success)

        # Write version 3 and commit it as a regular commit so that a revert to Version 2 has actual changes to commit
        db.write_scene(scene_uuid, text="Version 3", notes="Notes 3", synopsis="Syn 3")
        subprocess.run(
            ["git", "add", "Manuscript/"],
            cwd=db.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Regular user commit"],
            cwd=db.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # Verify current state
        sf_curr = db.read_scene(scene_uuid)
        self.assertEqual(sf_curr.text, "Version 3")

        # Revert to last snapshot (Snapshot 2 / Version 2)
        revert_res = db.revert_scene_to_last_snapshot(scene_uuid)
        self.assertEqual(revert_res["status"], "success")

        sf_reverted = db.read_scene(scene_uuid)
        self.assertEqual(sf_reverted.text, "Version 2")
        self.assertEqual(sf_reverted.notes, "Notes 2")
        self.assertEqual(sf_reverted.synopsis, "Syn 2")

        # Check git log to see both snapshots and revert commit exist
        res_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=db.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        log_text = res_log.stdout
        self.assertIn(f"[Snapshot] {scene_uuid}: First Snapshot", log_text)
        self.assertIn(f"[Snapshot] {scene_uuid}: Second Snapshot", log_text)
        self.assertIn(f"[Revert] {scene_uuid} to snapshot", log_text)

        # Now revert again: since we made a revert commit, the last snapshot commit remains Snapshot 2.
        # Let's write Version 4, commit it, then revert. It should go back to Version 2.
        db.write_scene(scene_uuid, text="Version 4")
        subprocess.run(
            ["git", "add", "Manuscript/"],
            cwd=db.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Another regular commit"],
            cwd=db.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        db.revert_scene_to_last_snapshot(scene_uuid)
        self.assertEqual(db.read_scene(scene_uuid).text, "Version 2")

    def test_image_storage_operations(self):
        db = GitBookDb.create_new(self.temp_dir, "ImageBook")
        outline = db.get_outline()
        notes_uuid = next(n.uuid for n in outline if n.title == FOLDER_NOTES)

        # Create a dummy image file outside the project
        external_dir = tempfile.mkdtemp()
        dummy_image_path = os.path.join(external_dir, "test_cover.png")
        dummy_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
        with open(dummy_image_path, "wb") as f:
            f.write(dummy_content)

        try:
            # 1. Test copy_image_into_project
            image_uuid = db.copy_image_into_project(dummy_image_path, notes_uuid, "cover_art")
            self.assertEqual(image_uuid, "Notes/cover_art.png")

            # Verify added to outline
            updated_outline = db.get_outline()
            notes_node = next(n for n in updated_outline if n.title == FOLDER_NOTES)
            self.assertEqual(len(notes_node.children), 1)
            image_node = notes_node.children[0]
            self.assertEqual(image_node.title, "cover_art.png")
            self.assertEqual(image_node.type, "Image")

            # Verify file exists on disk
            image_disk_path = os.path.join(db.project_path, "Notes", "cover_art.png")
            self.assertTrue(os.path.exists(image_disk_path))

            # 2. Test read_image_bytes
            read_bytes, mime_type = db.read_image_bytes(image_uuid)
            self.assertEqual(read_bytes, dummy_content)
            self.assertEqual(mime_type, "image/png")

            # 3. Test copy_image_from_project
            # Copy to a file path
            dest_file = os.path.join(external_dir, "copied_cover.png")
            db.copy_image_from_project(image_uuid, dest_file)
            self.assertTrue(os.path.exists(dest_file))
            with open(dest_file, "rb") as f:
                self.assertEqual(f.read(), dummy_content)

            # Copy to a directory
            dest_dir = os.path.join(external_dir, "output_dir")
            os.makedirs(dest_dir, exist_ok=True)
            db.copy_image_from_project(image_uuid, dest_dir)
            copied_in_dir = os.path.join(dest_dir, "cover_art.png")
            self.assertTrue(os.path.exists(copied_in_dir))
            with open(copied_in_dir, "rb") as f:
                self.assertEqual(f.read(), dummy_content)

            # 4. Test validation errors
            # Source file doesn't exist
            with self.assertRaises(FileNotFoundError):
                db.copy_image_into_project("non_existent_image.png", notes_uuid, "fail")

            # Target is not a folder
            with self.assertRaises(ValueError):
                db.copy_image_into_project(dummy_image_path, image_uuid, "fail")

            # Image node doesn't exist
            with self.assertRaises(ValueError):
                db.read_image_bytes("non_existent_uuid")
            with self.assertRaises(ValueError):
                db.copy_image_from_project("non_existent_uuid", dest_dir)

        finally:
            shutil.rmtree(external_dir)

    def test_unsupported_engines_raise_not_implemented(self):
        # Test ScrivenerBookDb stubs
        from mcp_server.engine.scrivener_engine import ScrivenerBookDb
        # Create a mock Scrivener project directory structure
        scriv_dir = os.path.join(self.temp_dir, "MockScriv.scriv")
        os.makedirs(os.path.join(scriv_dir, "Files"), exist_ok=True)
        # Create a basic binder .scrivx file
        scrivx_path = os.path.join(scriv_dir, "MockScriv.scrivx")
        with open(scrivx_path, "w", encoding="utf-8") as f:
            f.write('<ScrivenerProject Version="1.0"><Binder></Binder></ScrivenerProject>')
        
        scriv_db = ScrivenerBookDb(scriv_dir)
        with self.assertRaises(NotImplementedError):
            scriv_db.copy_image_into_project("dummy.png", "some_uuid", "img")
        with self.assertRaises(NotImplementedError):
            scriv_db.copy_image_from_project("some_uuid", "dest_dir")
        with self.assertRaises(NotImplementedError):
            scriv_db.read_image_bytes("some_uuid")
        with self.assertRaises(NotImplementedError):
            scriv_db.generate_kdp_cover("some_uuid", "kdp_cov")

        # Test InMemoryDb stubs
        from mcp_server.engine.in_memory_engine import InMemoryDb
        mem_db = InMemoryDb("InMemoryProject")
        with self.assertRaises(NotImplementedError):
            mem_db.copy_image_into_project("dummy.png", "some_uuid", "img")
        with self.assertRaises(NotImplementedError):
            mem_db.copy_image_from_project("some_uuid", "dest_dir")
        with self.assertRaises(NotImplementedError):
            mem_db.read_image_bytes("some_uuid")
        with self.assertRaises(NotImplementedError):
            mem_db.generate_kdp_cover("some_uuid", "kdp_cov")

    def test_generate_kdp_cover(self):
        db = GitBookDb.create_new(self.temp_dir, "KDPBook")
        outline = db.get_outline()
        notes_uuid = next(n.uuid for n in outline if n.title == FOLDER_NOTES)

        # Create a tiny dummy image file outside the project (aspect ratio 1:1, 100x100 pixels)
        from PIL import Image
        external_dir = tempfile.mkdtemp()
        dummy_image_path = os.path.join(external_dir, "test_input.png")
        
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(dummy_image_path)

        try:
            # Copy dummy image into project first
            source_uuid = db.copy_image_into_project(dummy_image_path, notes_uuid, "original_art")
            
            # Generate KDP cover
            kdp_uuid = db.generate_kdp_cover(source_uuid, "my_kdp_cover")
            self.assertEqual(kdp_uuid, "Notes/my_kdp_cover.jpg")

            # Verify added to outline
            updated_outline = db.get_outline()
            notes_node = next(n for n in updated_outline if n.title == FOLDER_NOTES)
            self.assertEqual(len(notes_node.children), 2)
            kdp_node = next(c for c in notes_node.children if c.title == "my_kdp_cover.jpg")
            self.assertEqual(kdp_node.type, "Image")

            # Verify physical file details on disk
            dest_disk_path = os.path.join(db.project_path, "Notes", "my_kdp_cover.jpg")
            self.assertTrue(os.path.exists(dest_disk_path))

            # Verify image properties using PIL
            with Image.open(dest_disk_path) as kdp_img:
                self.assertEqual(kdp_img.format, "JPEG")
                self.assertEqual(kdp_img.size, (1600, 2560))
                # Check DPI metadata
                dpi = kdp_img.info.get("dpi")
                self.assertEqual(dpi, (300, 300))

            # Test duplicate call just overwrites file and returns same UUID
            kdp_uuid_again = db.generate_kdp_cover(source_uuid, "my_kdp_cover")
            self.assertEqual(kdp_uuid_again, kdp_uuid)
            self.assertEqual(len(db.get_outline()[3].children), 2)

        finally:
            shutil.rmtree(external_dir)

    def test_generate_kdp_cover_file_size_check(self):
        db = GitBookDb.create_new(self.temp_dir, "KDPSizeBook")
        outline = db.get_outline()
        notes_uuid = next(n.uuid for n in outline if n.title == FOLDER_NOTES)

        from PIL import Image
        external_dir = tempfile.mkdtemp()
        dummy_image_path = os.path.join(external_dir, "test_input.png")
        
        img = Image.new("RGB", (100, 100), color="red")
        img.save(dummy_image_path)

        try:
            source_uuid = db.copy_image_into_project(dummy_image_path, notes_uuid, "original_art")

            # 1. Test fallback to quality=75 when size > 5MB
            # We want getsize to return 6MB first, then 3MB (after quality reduction save)
            from unittest.mock import patch
            
            with patch("os.path.getsize") as mock_getsize:
                mock_getsize.side_effect = [6 * 1024 * 1024, 3 * 1024 * 1024]
                
                # This should run successfully because the second size check returns 3MB (under 5MB limit)
                kdp_uuid = db.generate_kdp_cover(source_uuid, "fallback_cover")
                self.assertEqual(kdp_uuid, "Notes/fallback_cover.jpg")
                
                # Should have called getsize twice (once for initial check, once after re-save)
                self.assertEqual(mock_getsize.call_count, 2)

            # 2. Test ValueError when size remains > 5MB even after fallback
            with patch("os.path.getsize") as mock_getsize:
                # Both checks return 6MB (over 5MB limit)
                mock_getsize.return_value = 6 * 1024 * 1024
                
                with self.assertRaises(ValueError) as context:
                    db.generate_kdp_cover(source_uuid, "oversized_cover")
                
                self.assertIn("exceeds the 5MB limit even after quality reduction", str(context.exception))
                
                # File should have been cleaned up and deleted
                dest_path = os.path.join(db.project_path, "Notes", "oversized_cover.jpg")
                self.assertFalse(os.path.exists(dest_path))

        finally:
            shutil.rmtree(external_dir)

    def test_epub_cover_integration(self):
        # 1. Create a GitBook project
        db = GitBookDb.create_new(self.temp_dir, "GPUBook")
        db.create_agent_workspace()
        
        # 2. Add some Manuscript chapters/scenes to make it valid
        outline = db.get_outline()
        ms_node = next(n for n in outline if n.type == TYPE_DRAFT_FOLDER)
        ch_uuid = db.create_binder_item(ms_node.uuid, "Chapter 1", "Folder")
        sc_uuid = db.create_binder_item(ch_uuid, "Scene 1", "Text")
        db.write_scene(sc_uuid, text="Hello world manuscript content.")
        
        # 3. Get the Prompt Directives node
        pd_node = next((n for n in outline if n.title.lower() == "prompt directives"), None)
        if not pd_node:
            for n in outline:
                for c in n.children:
                    if c.title.lower() == "prompt directives":
                        pd_node = c
                        break
        self.assertIsNotNone(pd_node)
        pd_uuid = pd_node.uuid
        
        # 4. Set up an external image (non-compliant 100x100 PNG)
        from PIL import Image
        external_dir = tempfile.mkdtemp()
        external_img_path = os.path.join(external_dir, "ext_cover.png")
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(external_img_path)
        
        try:
            # Write Prompt Directives notes metadata table referencing the external cover
            metadata_notes = (
                "### Agent Metadata\n"
                "| Attribute | Value |\n"
                "| --- | --- |\n"
                "| Title | GPUBook |\n"
                "| Author | Tester |\n"
                f"| Cover | {external_img_path} |\n"
            )
            db.write_scene(pd_uuid, notes=metadata_notes)
            
            # 5. Call build_epub
            from mcp_server.renderer import build_epub
            output_epub = os.path.join(external_dir, "test_out.epub")
            
            build_epub(db, output_epub)
            
            self.assertTrue(os.path.exists(output_epub))
            
            # 6. Check that:
            # - The external image was copied into the project and KDP-formatted
            # - The Prompt Directives cover metadata was updated with the new KDP cover's UUID
            updated_pd = db.read_scene(pd_uuid)
            self.assertIn("Cover", updated_pd.notes)
            self.assertIn("_kdp_cover.jpg", updated_pd.notes)
            
            # Validate the EPUB zip container contains the cover image
            import zipfile
            with zipfile.ZipFile(output_epub, "r") as epub:
                cover_file_in_epub = next((f for f in epub.namelist() if "ext_cover_kdp_cover.jpg" in f), None)
                self.assertIsNotNone(cover_file_in_epub)
                
                # Check manifest/metadata in content.opf
                opf_content = epub.read("OEBPS/content.opf").decode("utf-8")
                self.assertIn('properties="cover-image"', opf_content)
                self.assertIn('<meta name="cover" content="cover-image"/>', opf_content)
                
        finally:
            shutil.rmtree(external_dir)

    def test_generate_kdp_cover_removes_watermark(self):
        db = GitBookDb.create_new(self.temp_dir, "KDPWatermarkBook")
        outline = db.get_outline()
        notes_uuid = next(n.uuid for n in outline if n.title == FOLDER_NOTES)

        from PIL import Image
        external_dir = tempfile.mkdtemp()
        dummy_image_path = os.path.join(external_dir, "test_input.png")
        
        img = Image.new("RGB", (100, 100), color="green")
        img.save(dummy_image_path)

        try:
            source_uuid = db.copy_image_into_project(dummy_image_path, notes_uuid, "original_art")
            
            from unittest.mock import MagicMock, patch
            mock_remove = MagicMock(side_effect=lambda img: img)
            
            with patch("remove_ai_watermarks.gemini_engine.GeminiEngine.remove_watermark", mock_remove):
                kdp_uuid = db.generate_kdp_cover(source_uuid, "watermarked_cover")
                self.assertEqual(kdp_uuid, "Notes/watermarked_cover.jpg")
                mock_remove.assert_called_once()
                
        finally:
            shutil.rmtree(external_dir)

    def test_server_tools_gitbook(self):
        from mcp_server.server import (
            clone_project_structure_tool,
            create_new_book,
            create_project_from_schema_tool,
        )
        # Test create_new_book programmatically
        res = create_new_book(self.temp_dir, "ServerGBBook", format="gitbook")
        self.assertIn("Successfully created new book", res["content"][0]["text"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "ServerGBBook.gitbook")))
        
        # Test create_project_from_schema programmatically
        schema = [
            {"title": "Chapter 1", "type": "Folder", "children": [
                {"title": "Scene A", "type": "Text", "text": "Prose"}
            ]}
        ]
        res_schema = create_project_from_schema_tool(self.temp_dir, "SchemaGBBook", schema, format="gitbook")
        self.assertIn("Successfully generated new book", res_schema["content"][0]["text"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "SchemaGBBook.gitbook")))
        
        # Test clone_project_structure programmatically
        res_clone = clone_project_structure_tool(
            os.path.join(self.temp_dir, "SchemaGBBook.gitbook"),
            self.temp_dir,
            "CloneGBBook",
            format="gitbook"
        )
        self.assertIn("Successfully cloned structure", res_clone["content"][0]["text"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "CloneGBBook.gitbook")))


if __name__ == "__main__":
    unittest.main()

