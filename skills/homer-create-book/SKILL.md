---
name: homer-create-book
description: "Guides the author through bootstrapping a new book project in GitBook (.gitbook) format. Gathers metadata, model parameters, genre benchmarks, and layout constraints; extracts context/settings if it is a sequel to an existing book or project; designs outlines and chapter structures; and creates the project folder, agent workspace, and Codex template structure."
---

# Book Initialization and Creation Skill (`homer-create-book`)

This skill coordinates the creation and initialization of a new book project in GitBook (`.gitbook`) format. It guides you (the AI agent) through interviewing the author, handling settings/context reuse from sequels, designing story outlines, and instantiating the project files using the Homer MCP tools.

---

## 🔄 Book Creation Workflow

When `/homer-create-book` is invoked (or the author requests to start a new book), execute the following sequence:

### Step 1: Interview the Author

Conduct a structured interview with the author to gather critical project settings. **Always provide sensible defaults** so the author can easily hit Enter or confirm them.

1. **Basic Info**:
   * **Title**: Ask for the book's title.
   * **Author**: Ask for the author's name.
2. **Model Parameters (calibrated LLMs)**:
   * **Model**: Master steering/planning model (Default: `google/gemini-2.5-pro`)
   * **Drafting Model**: Prose generator model (Default: `anthropic/claude-sonnet-4.6`)
   * **Critique Model**: Structural/stylistic editor model (Default: `google/gemini-2.5-pro`)
3. **Genre & Benchmarks**:
   * **Genre**: Ask for the target genre (e.g., *Middle Grade*, *Young Adult*, *Sci-Fi*, *Thrillers*).
   * **Target Grade Level**: (Default: `5.5` for Middle Grade)
   * **Max Adverb Density**: (Default: `1.0%`)
   * **Max Passive Density**: (Default: `4.0%`)
   * **Max Filler Density**: (Default: `1.2%`)
4. **Layout / Formatting Info**:
   * Ask if they have target print parameters (e.g., Trim Width, Trim Height, margins, bleed).
   * Default values to offer:
     * *Trim Width*: `5.25 in`
     * *Trim Height*: `8.0 in`
     * *Bleed*: `No`
     * *Gutter*: `0.55 in`
     * *Outside Margin*: `0.35 in`
     * *Top Margin*: `0.75 in`
     * *Bottom Margin*: `0.75 in`
5. **Sequel Check**:
   * Ask: *"Is this book a sequel to an existing book?"*

---

### Step 2: Sequel Context Extraction (If Applicable)

If the book is a sequel, ask the author to provide the path to the previous book's project directory (`.gitbook` or `.scriv`) or rendered file (`.epub` or `.pdf`). Proceed to extract as much context as possible:

#### Option A: Previous Project Directory Available
If they point to a `.gitbook` or `.scriv` project path:
1. **Load settings**: Call `get_book_outline` on the source path. Find the `Prompt Directives` file (usually inside `[Agent Workspace]`).
2. **Read metadata & style**: Call `read_scene` on the `Prompt Directives` UUID to retrieve the exact metadata table (author, models, layout parameters) and writing guidelines.
3. **Scan Codex (Characters, Places, Lore)**: Locate the `Codex/` subfolders or main outline character files. Collect names, descriptions, and details that should carry over.
4. **Scan Continuity/Bible**: Retrieve continuity lists or styling notes from `Notes/Editor/` folders (such as `_Continuity_Bible.json` or `.md`) to maintain consistent facts.

#### Option B: Rendered EPUB Available
If only a rendered EPUB is available, write and execute a temporary Python script (or call a command) to extract title, creator/author, publisher, and basic metadata.
* **EPUB Metadata Parser Helper Command**:
  ```bash
  python3 -c "import zipfile, xml.etree.ElementTree as ET; z = zipfile.ZipFile('path/to/book.epub'); opf = ET.fromstring(z.read(ET.fromstring(z.read('META-INF/container.xml')).find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile').attrib['full-path'])); print({e.tag.split('}')[-1]: e.text for e in opf.iter() if any(x in e.tag.lower() for x in ['title', 'creator', 'publisher', 'language'])})"
  ```
  *(Execute this inside the workspace shell to extract initial settings).*

#### Option C: Rendered PDF Available
If only a PDF is available, attempt to read the PDF metadata using Python standard library or basic parsing, or ask the author to paste/provide a summary of key character lore and world rules they want to preserve.

*Present the synthesized settings (Title, Author, Genre benchmarks, Models, Margins) and a list of characters/settings to import to the author for confirmation.*

---

### Step 3: Outline, Characters, & Settings Discussion (Optional)

Ask: *"Would you like to generate a starting outline, key characters, and location profiles for this book?"*

1. **Discuss the Storyline, Characters, & Settings**:
   * **Storyline**: Discuss the plot arc, main narrative conflicts, division into parts/acts (e.g., Act 1, Act 2, Act 3), and pacing.
   * **Characters**: Discuss the key characters. For each character, co-design their full name, aliases, age, role/narrative function, physical description/mannerisms, background/motivations, relationships, and chronological states.
   * **Settings**: Discuss key locations where the action takes place (name, description, atmosphere, import to narrative).
2. **Design Outline Schema & Codex Entries**:
   * Synthesize the outline discussion into a chapter-by-chapter structure.
   * For each chapter/scene, draft a brief title and a 1-2 sentence synopsis beat.
   * Express this outline as a standard JSON schema format for the creation tool:
     ```json
     [
       {
         "title": "Part One: Heading",
         "type": "Folder",
         "children": [
           {
             "title": "Chapter 1",
             "type": "Folder",
             "children": [
               {
                 "title": "Scene Name",
                 "type": "Text",
                 "synopsis": "Beat description...",
                 "notes": "Reference notes..."
               }
             ]
           }
         ]
       }
     ]
     ```

---

### Step 4: Create the Project

Once settings, outline, and characters are finalized, initialize the new project using one of the following two options to avoid structural conflicts:

#### Option A: Starting Outline is Requested
If the author wants a starting outline structure:
1. **Create Project with Outline**:
   * Call `create_project_from_schema` with the target directory, book name, format `"gitbook"`, and the designed outline JSON schema.
   * *Note: The new project directory will be created under `books/` in the workspace (e.g., `books/MyNewBook.gitbook`).*
2. **Initialize Workspace**:
   * Call `create_agent_workspace` on the newly created project path to build the `[Agent Workspace]` folder and base templates.

#### Option B: Blank Project (No Outline)
If the author wants a clean slate with no starting outline structure:
1. **Create Blank Project**:
   * Call `create_new_book` with the target directory, book name, and format `"gitbook"`.
2. **Initialize Workspace**:
   * Call `create_agent_workspace` on the newly created project path to build the `[Agent Workspace]` folder and base templates.

---

### Step 5: Seed Metadata, Benchmarks, and Codex

Once the project and its workspace are created, populate settings and continuity context:

1. **Seed Metadata & Benchmarks**:
   * Find the `Prompt Directives` document inside `[Agent Workspace]` by scanning the project outline.
   * Update its notes section by calling `write_scene` (passing the project path, UUID, and title/text/notes).
   * Seed the exact tables for `Agent Metadata` and `Genre Benchmarks` matching the confirmed interview parameters:
     ```markdown
     ### Agent Metadata
     | Attribute | Value |
     | --- | --- |
     | Title | [Title] |
     | Author | [Author] |
     | Model | [Model] |
     | Drafting Model | [Drafting Model] |
     | Critique Model | [Critique Model] |
     | Trim Width | [Trim Width] |
     | Trim Height | [Trim Height] |
     | Bleed | [Bleed] |
     | Gutter | [Gutter] |
     | Outside Margin | [Outside Margin] |
     | Top Margin | [Top Margin] |
     | Bottom Margin | [Bottom Margin] |

     ### Genre Benchmarks
     | Attribute | Value |
     | --- | --- |
     | Genre | [Genre] |
     | Target Grade Level | [Grade Level] |
     | Max Adverb Density | [Max Adverb] |
     | Max Passive Density | [Max Passive] |
     | Max Filler Density | [Max Filler] |
     ```
2. **Seed Codex Character and Location Profiles**:
   * Retrieve the outline structure of the newly created book and find the UUIDs for `[Agent Workspace]/Codex/Characters` and `[Agent Workspace]/Codex/Places`.
   * For **each key character** discussed:
     * Call `create_binder_item` (with `item_type="Text"`) under the `Characters` folder to create a new profile node.
     * Call `write_scene` to seed the main profile text (using a clear structure covering role, appearance, background), the metadata/relationships tables in the notes pane, and a short summary in the synopsis.
   * For **each key location** discussed:
     * Call `create_binder_item` (with `item_type="Text"`) under the `Places` folder.
     * Call `write_scene` to seed the location profile text, notes table, and synopsis.
3. **Seed Sequel Codex Continuity (Sequels Only)**:
   * For characters/places imported from a sequel project/EPUB, locate the subfolders under `[Agent Workspace]/Codex/`.
   * Call `create_binder_item` and `write_scene` to populate them with the parsed descriptions and notes.

Confirm to the author that the project has been fully initialized and present the folder structure link to start drafting.

---

## 🛠️ MCP Tool Reference

Use these tools to execute the book creation:

1. `create_new_book` (Creates a blank gitbook/scrivener project with base folders. Specify `format="gitbook"`).
2. `create_agent_workspace` (Initializes boilerplate files inside `[Agent Workspace]`).
3. `create_project_from_schema` (Creates folder/scene hierarchies from a custom JSON schema).
4. `create_binder_item` (Inserts a folder/scene at a specific node).
5. `write_scene` (Writes text, notes, synopsis, and metadata tables).
6. `get_book_outline` (Retrieves structural tree for sequels/outlines).
7. `read_scene` (Reads source metadata for sequels).
