---
name: homer-prose-polish
description: "Optimized diagnostic and progressive prose polish loop for Scrivener scene drafts. Guides the agent to analyze text against genre benchmarks and execute safe, native snapshot-backed AI revisions exclusively via MCP tools."
---

# Prose Polish Loop Skill (`homer-prose-polish`)

This skill provides a self-contained, optimized workflow to analyze, critique, and progressively polish story drafts inside Scrivener (.scriv) projects. 

Rather than writing custom code or modifying complex XML files directly, you will act as a coordinator—orchestrating high-level **Model Context Protocol (MCP)** tools to safely backup drafts, compute quantitative readability scores, generate qualitative editorial reports, and apply refined updates directly to the Scrivener binder database.

---

## 🚫 Critical Guardrail: Strict Tool Delegation

> [!CRITICAL]
> **NEVER write custom Python scripts, run shell file-modification commands, or manually edit any files inside a `.scriv` package.**
> Scrivener projects are complex directory databases of XML metadata and RTF files. Direct file manipulation or script-based writes will corrupt the project or cause desktop Scrivener to silently overwrite your changes.
> **You MUST delegate all analysis, backup, and rewrite operations exclusively to the Scrivener MCP server tools.**

> [!IMPORTANT]
> **⏳ Long-Running Operations & Timeouts**:
> The `generate_chapter_critique` and `apply_critique_to_scene` tools perform deep AI model analysis and full-length draft polishing. These operations are computationally heavy and can take **30 to 90 seconds** to finish.
> - **Expect Latency**: Do not assume tool failure or prematurely cancel executions when these operations are in progress.
> - **Timeout Requirements**: To prevent client-side timeouts, ensure OpenCode's configuration file (`~/.config/opencode/opencode.jsonc`) is configured to allow up to 15 minutes (`900000` ms) for MCP operations via `"experimental": { "mcp_timeout": 900000 }` and `"timeout": 900000` on the `homer-scrivener` server.

---

## 📊 The 5-Step Optimized Prose Polish Loop

To polish a scene draft, execute the following strict sequence of operations:

### Step 1: Pre-flight, Session Check & Discovery
1. **Prerequisite Check**: If no project has been initialized in the current session yet (i.e. you do not have the active project path or general guidelines loaded), first execute the `/homer-init` workflow to identify the project and load style guides and narrative memory.
2. **Locate Project**: Call `list_books` to locate the absolute path of the target Scrivener (`.scriv`) project.
3. **Find Scene UUID**: Call `get_book_outline` with the `project_path` to view the binder hierarchy. Map the target scene name (e.g. "Alone at the Ironworks") to its unique 36-character UUID (e.g. `BDD65B66-7558-46DA-836A-E7A64BBE27F0`).
   * *Note: If desktop Scrivener is running locally, the MCP server will safely block any modifying commands. If a block occurs, request the user to close desktop Scrivener before continuing.*
4. **Task Checklist Update**: Using the UUID of the `Task Checklist` document, read the checklist using `read_scene`. Locate the checklist item corresponding to polishing this chapter or scene (e.g., `- [ ] Polish Chapter X` or `- [ ] Sensory expanders`), update its checkbox indicator to in-progress (`- [/]`), and write the change back to the checklist document using the `patch_scene` tool.
5. **Session Memory Update**: Read the `Session Memory` document using `read_scene`. Locate and update the `Last Active State` to `"Polishing Scene: [Scene Name]"` (where [Scene Name] is the target scene title) and update the `Last Sync` timestamp. Use the `patch_scene` tool to save these updates.

### Step 2: Readability & Critique Diagnostic
1. **Run Critique**: Call `generate_chapter_critique` with the `project_path` and `scene_uuid`.
   * *Token Optimization: Do NOT call `read_scene` first. The critique tool reads the RTF draft natively from disk, saving massive tokens.*
2. **Inspect the Scorecard**: The tool returns a comprehensive standardized critique containing a quantitative scorecard:
   * **FKGL Grade Level** (Flesch-Kincaid)
   * **FRE Reading Ease** (Flesch)
   * **Average Sentence Length**
   * **Adverb Density** (words ending in `-ly`, excluding exceptions)
   * **Passive Voice Density**
   * **Filler Word Density**
   * **N-Gram Word & Phrase Repetitions**
3. **Analyze**: Evaluate the critique's Editorial Diagnosis and Actionable Revision Instructions. Report the starting scorecard to the user.

### Step 3: Critique Application & Snapshot Backup
1. **Apply Polish**: Call `apply_critique_to_scene` with the `project_path`, `scene_uuid`, and the `critique_text` report generated in Step 2.
2. **Snapshot Safety**: The tool **automatically** creates a native Scrivener XML backup snapshot named *"Before AI Style Critique Polish"* before making any changes. This snapshot displays natively inside desktop Scrivener's Inspector pane and supports full visual comparisons and rollbacks.
3. **Rewrite Prose**: The tool calls the writer engine to rewrite the scene draft, applying all revision guidelines while strictly preserving character voice and story beats. The updated text is written directly into Scrivener.

### Step 4: Verify and Progressive Loop
1. **Run Verification**: Call `generate_chapter_critique` again on the newly polished scene.
2. **Compare Scores**: Contrast the new metrics against the target benchmarks (Middle Grade, Young Adult, or Adult).
3. **Loop if Needed**: If any core metric (e.g., Grade Level or Passive Voice) is still significantly out of bounds, run **Step 3 (Apply Critique)** and **Step 4 (Verify)** again.
   * *Constraint: Limit your progressive edits to a maximum of 3 iterations to prevent style homogenization.*

### Step 5: Handoff & Rollback Instructions
1. **Report Progress**: Present the user with a comparative scorecard tracking metrics from the *Initial Draft* to the *Final Polished Draft*.
2. **Expose Snapshots**: Inform the user that the polished scene has been updated. Explain how they can open Scrivener and review the native backups:
   > Open desktop Scrivener, navigate to the scene in your Binder, click the **Inspector** pane on the right, and select the **Snapshots** tab (the camera icon). You will find all historical versions listed there with timestamps, where you can natively compare or roll back changes!
3. **Task Checklist Update**: Read the `Task Checklist` document using `read_scene`. Locate the checklist item corresponding to polishing this chapter or scene (which was marked as `- [/]`), update its checkbox indicator to completed (`- [x]`), and save the change using the `patch_scene` tool.
4. **Session Memory Update**: Read the `Session Memory` document using `read_scene`. Locate and update the `Last Active State` to `"Finished polishing Scene: [Scene Name]"` and update the `Last Sync` timestamp. Use the `patch_scene` tool to save these updates.



---

## 🛠️ MCP Tool Reference

Here are the specific tools you must call to execute the workflow:

### 1. `list_books`
* **Description**: Lists all Scrivener projects in the workspace.
* **Parameters**:
  * `search_path` (string, optional): Folder to search. Defaults to `./books`.
* **Returns**: A JSON array of books containing their display names and absolute paths.

### 2. `get_book_outline`
* **Description**: Retrieves the hierarchical binder outline structure of a project.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
* **Returns**: A hierarchical JSON tree of binder folders and texts, containing titles, UUIDs, and types.

### 3. `generate_chapter_critique`
* **Description**: Computes zero-token analytical metrics locally and generates a standardized, detailed editorial critique.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `scene_uuid` (string, required): UUID of the target Scene document.
  * `target_reading_level` (string, optional): Dynamic override (e.g., 'Middle Grade', 'Young Adult', 'Adult'). Defaults to dynamic project discovery.
* **Returns**: A Markdown report with a style scorecard, repeated n-grams, and paragraph-level revision instructions.

### 4. `apply_critique_to_scene`
* **Description**: Backs up the scene using a native XML snapshot and rewrites the draft to satisfy benchmarks.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the `.scriv` package.
  * `scene_uuid` (string, required): UUID of the target Scene document.
  * `critique_text` (string, optional): Standardized critique report. If omitted, automatically read from the scene's Notes.
* **Returns**: Status confirmation containing the snapshot details and the target genre targets applied.

---

## 🎨 Style Directives & Target Benchmarks

The Scrivener MCP server dynamically extracts genre benchmarks from tables inside your project's `Prompt Directives` binder notes. If no explicit table exists, it falls back to standard industry presets. Be aware of these ranges when explaining the scorecards:

| Metric | Middle Grade (MG) | Young Adult (YA) | General Adult Fiction |
| :--- | :--- | :--- | :--- |
| **FK Grade Level** | 4.5 – 6.5 | 6.0 – 8.0 | 7.0 – 10.0 |
| **Avg Sentence Length** | 10.0 – 14.0 words | 12.0 – 16.0 words | 14.0 – 18.0 words |
| **Max Adverb Density** | <= 1.0% | <= 1.3% | <= 1.6% |
| **Max Passive Voice** | <= 4.0% | <= 6.0% | <= 8.0% |
| **Max Filler Words** | <= 1.2% | <= 1.5% | <= 1.8% |

### 🎭 Preserving Voice & Tone (Critical Constraint)
While editing to meet grade level and readability targets (such as shortening overly complex sentences or removing weak passive voice constructions), **you must strictly protect the author's narrative identity.**
* Keep Achilles' **unique, sardonic, and self-aware voice** intact.
* Do NOT sanitize characters' dialogue or blunt their rough edges.
* Maintain tense consistency and specific sensory descriptions.
* Make edits **tactful and surgical**—never rewrite blocks of text that are already grammatically strong and stylistically correct.
