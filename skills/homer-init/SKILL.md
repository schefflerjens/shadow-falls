---
name: homer-init
description: "Initialize novel writing session, locate project files (Prompt Directives, Session Memory, Task Checklist) anywhere in the binder outline, establish creative writing delegation rules, and print a project-level progress summary matching the project's tone guidelines."
---

# Session Initialization Skill (`homer-init`)

This skill coordinates the "cold-start" process for a novel-writing session in Scrivener. It ensures you understand your role (assisting an author in writing a novel), establishes proper tool delegation, recursively locates the project configuration documents, and outputs a welcoming status report matching the style and tone guidelines defined inside the project (e.g., adopting Achilles' sardonic AI persona if initializing the Achilles/Bear Arms project, or matching the specific genre atmosphere of the selected book).

---

## 🚫 Critical Rule: Creative Writing Delegation

> [!IMPORTANT]
> **Do NOT write creative prose (scene drafts, beats, chapters, or large rewrites) directly in the chat panel.**
> The Scrivener MCP server is configured to run creative writing tasks using specialized, project-calibrated LLMs (configured dynamically via project variables or `Prompt Directives`). Generating prose in the chat panel bypasses these customized writer engines and breaks the connection to the binder's versioning and snapshot systems.
> - **Permitted in Chat**: Brainstorming, outlining plot points, analyzing readability reports, planning, character development, and general conversational feedback.
> - **Delegated to MCP**: Scene drafting (`generate_draft_beat`), scene rewriting and style-critique application (`apply_critique_to_scene`), and modifying scene text (`write_scene`, `patch_scene_tool`).

---

## 🔄 Cold-Start Sequence

When `/homer-init <project_name>` is invoked, execute the following sequence:

### Step 1: Locate Project Path
1. Call `list_books` to scan the workspace directories.
2. Locate the `.scriv` project matching the `<project_name>` argument (e.g., `/homer-init achilles` matches `achilles.scriv`).
3. If no project argument was provided, or if multiple projects match, list all discovered books to the user and ask them to select one.

### Step 2: Search Binder Recursively for Core Documents
1. Call `get_book_outline` with the project path to retrieve the hierarchical binder tree.
2. **Do NOT assume a strict folder structure.** Recursively traverse the outline tree to locate the UUIDs for these three key documents by title (case-insensitively):
   * `Prompt Directives`
   * `Session Memory`
   * `Task Checklist`
3. **Self-Healing Actions**:
   * If any of these files are missing, search for an `[Agent Workspace]` folder in the outline.
   * If `[Agent Workspace]` exists, use `create_binder_item` to create the missing document(s) inside it, then seed them with default templates.
   * If `[Agent Workspace]` is missing entirely, call `create_agent_workspace_tool` to initialize the standard workspace structure.

### Step 3: Load Context & Settings
1. Call `read_scene` on the UUIDs of `Prompt Directives`, `Session Memory`, and `Task Checklist` (and any other discovered project-level guidelines).
2. Extract the following context:
   * **Style Directives**: POV, narrative tense, genre benchmarks, and writing constraints.
   * **Narrative Memory**: Current active chapter, key plot elements, and last sync timestamp.
   * **Checklist**: Current tasks, completed items, and pending milestones.
3. **Scan Outline and Retrieve Real-time Metrics**:
   * To compile an accurate, up-to-date project commentary and checklist progress summary (Step 4), traverse the Manuscript outline and call the programmatic `get_scene_readability_metrics` tool on **all drafted/existing scenes** in the chapters.
   * **Do NOT read metrics or critique reports from the scene's notes pane.** These stored reports in notes are static and become outdated/stale when the drafts are updated.
   * **Use programmatic metrics only**: Calculate the fresh metrics for the scenes dynamically using `get_scene_readability_metrics`. Do NOT use `generate_chapter_critique` for this general scan to avoid unnecessary/expensive LLM calls.

### Step 4: Output Project Summary (Project-Specific Persona)
Print a stylized, project-level initialization summary to confirm you are up to speed.
* **Persona Constraints**: Adopt the voice, narrator persona, or style guidelines defined in `Prompt Directives` (for example, if the project is 'Bear Arms', adopt the voice of Achilles—the brilliant, sardonic, and pompous AI trapped in a robotic teddy bear; for other projects, match that project's specific style guide).
* **Summary Contents**:
  * **Status**: Acknowledge the target project and verify that the binder outline has been indexed.
  * **Steering Rules**: Confirm the active POV and narrative tense.
  * **Plot Memory**: Highlight key plot points or targets from `Session Memory`.
  * **Checklist progress**: List completed tasks and pending milestones from `Task Checklist` and specify fresh readability statistics (e.g. FKGL and passive voice counts computed in Step 3).
  * **Project Commentary**: Include a closing remark matching the book's persona or tone guidelines about the current state of progress or upcoming tasks.


### Step 5: Start the Web Viewer
1. Call the `start_web_viewer` tool with `port=8090` to boot up the background HTML web server.
2. Provide a link/URL (`http://localhost:8090`) in the chat to allow the author to view drafts in real-time.

---

## 🛠️ MCP Tool Reference for Initialization

Use these tools to run the sequence:

### 1. `list_books`
* **Description**: Lists all Scrivener projects in the workspace.
* **Parameters**: None required.

### 2. `get_book_outline`
* **Description**: Returns the hierarchical binder structure.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.

### 3. `create_agent_workspace_tool`
* **Description**: Initializes the default workspace structure if missing.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.

### 4. `create_binder_item`
* **Description**: Creates a new binder document or folder.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `parent_uuid` (string, required): UUID of the parent folder.
  * `title` (string, required): Document title.
  * `item_type` (string, optional): `"Text"` or `"Folder"`.

### 5. `read_scene`
* **Description**: Reads the text content of a binder document.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `uuid` (string, required): UUID of the document.

### 6. `start_web_viewer`
* **Description**: Starts the HTML background web server.
* **Parameters**:
  * `port` (integer, optional): Port number to start the server on. (Set to 8090 during initialization).

### 7. `get_scene_readability_metrics`
* **Description**: Computes readability indices and style metrics programmatically and locally without LLM calls.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the Scrivener project.
  * `scene_uuid` (string, required): UUID of the scene text document.



