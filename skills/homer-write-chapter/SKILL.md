---
name: homer-write-chapter
description: "Plan, outline, refine, and write a new book chapter. Handles preceding chapter continuity check, collaborative beat planning, auto-starting the Live Web Viewer with direct links, and executing sequential scene-by-scene drafts in Scrivener."
---

# Write Chapter Skill (`homer-write-chapter`)

This skill coordinates the collaborative, step-by-step planning and writing process for a new chapter in Scrivener. It ensures narrative continuity, guides beat outlining, manages the Live Web Viewer, and writes polished prose scene-by-scene.

---

## 🔄 The 6-Step Collaborative Writing Pipeline

When `/homer-write-chapter [chapter_name]` is invoked, execute the following workflow:

### Step 1: Target Chapter Selection & Session Check
1. **Prerequisite Check**: If no project has been initialized in the current session yet (i.e. you do not have the active project path or general guidelines loaded), first execute the `/homer-init` workflow to identify the project and load style guides, narrative memory, and task checklist.
2. Locate the absolute path of the current Scrivener project.
3. If the user specified a `[chapter_name]`, locate the matching folder in the binder outline (using `get_book_outline`).
4. If no name was specified, automatically scan the outline to find the **next unwritten chapter folder**:
   * An unwritten chapter is a binder item of type `Folder` under the Manuscript outline that has either no child documents, or whose child documents are entirely empty (0 words/empty RTF content).
5. Fetch the synopsis of the selected chapter folder. If the chapter synopsis is missing, ask the user to provide a high-level synopsis/premise for the chapter before proceeding.
6. **Task Checklist Update**: Using the UUID of the `Task Checklist` document, read the checklist using `read_scene`. Locate the checklist item corresponding to drafting this chapter (e.g., `- [ ] Draft Chapter X` or `- [ ] Chapter X`), update its checkbox indicator to in-progress (`- [/]`), and write the change back to the checklist document using the `patch_scene` tool.
7. **Session Memory Update**: Read the `Session Memory` document using `read_scene`. Locate and update the `Last Active State` to `"Drafting Chapter X"` (where X is the chapter name/number) and update the `Last Sync` timestamp. Use the `patch_scene` tool to save these updates.

### Step 2: Continuity Context Check
1. Search the binder outline for the sibling chapter folder that immediately precedes the target chapter.
2. If a preceding chapter is found:
   * Load its synopsis (and/or the draft text of its final scene).
   * Present the user with a brief **Continuity Summary** detailing:
     * How the previous chapter ended.
     * Where the new chapter is slated to begin.
     * How this transition fits the book's overarching narrative pacing.

### Step 3: Collaborative Beat Discussion
1. Ask the user if they have any specific parameters, themes, character choices, or plot details they want to work into this chapter's beats.
2. Discuss and iterate on these details in the chat.
3. **Wait for the user's explicit approval ("thumbs up")** before proceeding to beat generation.

### Step 4: Beat Generation
1. Call the MCP tool `generate_chapter_beats_tool` with:
   * `project_path`: Path to the `.scriv` package.
   * `chapter_folder_uuid`: UUID of the selected chapter folder.
   * `num_scenes`: Number of scenes to generate (default to 3, or user-preferred).
   * `custom_beats_prompt`: A summarized string of all decisions and details agreed upon during Step 3.
2. This tool will automatically partition the chapter synopsis, create corresponding scene documents in the Scrivener binder, and write the generated beats into their respective synopses.

### Step 5: Web UI Review & Refinement
1. Check the status of the Live Web Viewer using `get_web_viewer_status_tool`.
2. If it is stopped or not active:
   * Call `start_web_viewer_tool(port=8090)` (or other default port).
3. Construct a direct link to the chapter folder:
   * **URL Format**: `http://localhost:<port>/?project_path=<url_encoded_project_path>&uuid=<chapter_folder_uuid>`
4. Present the list of generated scene beats to the user in chat, and provide the direct URL.
5. Instruct the user to click the link to edit and refine the scene synopses/beats in the Web UI or in Scrivener.
6. **Wait for the user's confirmation** that the beats are polished and ready for writing.

### Step 6: Sequential Prose Drafting
1. Once the user approves the beats and gives the go-ahead, start the drafting process.
2. **Draft Scenes Sequentially (Scene 1, then Scene 2, then Scene 3...)**:
   * For each scene document UUID under the chapter folder in draft order:
     * Call `generate_draft_beat` with the scene's UUID.
     * *Why this is critical*: `generate_draft_beat` automatically compiles `manuscript_so_far` from disk. By drafting sequentially, Scene 2's prompt will automatically contain the actual finished prose of Scene 1. This guarantees flawless narrative transitions and prevents style or plot drift.
     * Report progress in chat as each scene's prose draft is written and saved to disk.
3. Once all scenes in the chapter are drafted, announce completion and direct the user to the Web Viewer to review, critique, or polish the full chapter.
4. **Task Checklist Update**: Read the `Task Checklist` document using `read_scene`. Locate the checklist item corresponding to drafting this chapter (which was marked as `- [/]`), update its checkbox indicator to completed (`- [x]`), and save the change using the `patch_scene` tool.
5. **Session Memory Update**: Read the `Session Memory` document using `read_scene`. Update the `Last Active State` to `"Finished drafting Chapter X"` and update the `Last Sync` timestamp. Use the `patch_scene` tool to save these updates.



---

## 🛠️ MCP Tool Reference for Drafting

Use these tools to run the pipeline:

### 1. `get_book_outline`
* **Description**: Returns the hierarchical binder structure.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.

### 2. `get_scene_files`
* **Description**: Reads scene text, notes, and synopsis.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `uuid` (string, required): UUID of the document.

### 3. `generate_chapter_beats_tool`
* **Description**: Partitions chapter synopsis and creates scene documents.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `chapter_folder_uuid` (string, required): Chapter folder UUID.
  * `num_scenes` (integer, optional): Number of scenes (default: 3).
  * `custom_beats_prompt` (string, optional): Custom beats constraints.

### 4. `get_web_viewer_status_tool`
* **Description**: Returns web viewer port and status.

### 5. `start_web_viewer_tool`
* **Description**: Starts web viewer thread.
* **Parameters**:
  * `port` (integer, optional): Default is 8080 or 8090.

### 6. `generate_draft_beat`
* **Description**: Assembles context and writes the scene's prose draft.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `scene_uuid` (string, required): UUID of the scene text document.
  * `custom_instructions` (string, optional): Custom style steering.
