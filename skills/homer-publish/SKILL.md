---
name: homer-publish
description: "Validates book metadata (Title, Author) in the project, collects user feedback to update/insert missing metadata, prompts for output options (format, target location), and renders the compiled manuscript using the MCP render tool."
---

# Book Publishing Skill (`homer-publish`)

This skill coordinates checking project-level metadata (such as book Title and Author) in the binder, collecting user feedback to update or insert missing metadata, and rendering the compiled manuscript into a published ebook file (such as Kindle-compatible EPUB) or a compiled Markdown file using the Scrivener/GitBook database engine.

---

## 🔄 Publishing Sequence

When `homer-publish` is invoked, execute the following sequence:

### Step 1: Check Project Metadata
1. Call `get_book_outline` with the project path to retrieve the binder tree.
2. Locate the `Prompt Directives` document UUID (typically under the `[Agent Workspace]` folder).
3. Call `read_scene` on the `Prompt Directives` UUID.
4. Inspect the `notes` field for the `### Agent Metadata` or `### Metadata` section.
5. Parse the metadata table to check if **Title**, **Author**, and **Cover** attributes are defined.

### Step 2: Request User Feedback on Metadata
1. Present the current metadata values (Title, Author, and Cover image path/UUID) to the user in the chat panel.
2. If `Title` or `Author` is missing, highlight it and prompt the user to provide correct values.
3. Point out what cover image is configured (if any). Ask the user if the Title, Author, and Cover are correct, or if they would like to adjust/set them before publishing.
4. Inform the user that they can set the Cover to:
   - An existing image in the project (by UUID or filename).
   - An external image anywhere else on disk (by absolute path).

### Step 3: Update Binder Metadata
If the user provides updates or supplies missing metadata (including cover changes):
1. Reconstruct the metadata Markdown table block containing the correct attributes (e.g., `Title`, `Author`, `Cover`, `Model`, etc.).
2. Call **`write_scene`** (or **`patch_scene`**) to save the updated notes content back to the `Prompt Directives` document in the binder.
3. Call `read_scene` again to verify that the updates have been saved correctly.
4. *Note*: If the user specifies an external image path or an unformatted image as the cover, the backend **`render`** tool will automatically copy, format (upscale, center-crop, convert to KDP-compliant JPEG), register it in the binder, and update this `Cover` metadata entry during compilation.

### Step 4: Prompt for Format and Destination
1. Ask the user what format they would like to export to (supported values are:
   - `"amazon"` for Kindle-compatible EPUB.
   - `"pdf"` for print-ready paperback PDF (Amazon KDP compliant).
   - `"markdown"` for a compiled Markdown document).
2. If the user selects `"pdf"`, prompt them for print layout settings. Present the defaults from the project notes if they exist, or recommend standard KDP defaults:
   - **Trim Size**: Width x Height in inches (common defaults: `6.0` x `9.0` or `5.5` x `8.5`).
   - **Bleed**: True/False (Yes/No if pages have images or background colors extending to the edge).
   - **Gutter / Inside Margin**: Gutter size in inches (or `auto` to dynamically calculate based on page count).
   - **Outside Margins**: Margin size in inches (minimum 0.25 for no bleed, 0.375 for bleed).
3. Prompt the user for the absolute file path where the rendered file should be saved (e.g., `/Users/jensscheffler/projects/homer/books/Bear with me.epub`, `/Users/jensscheffler/projects/homer/books/Bear with me.pdf`, or `/Users/jensscheffler/projects/homer/books/Bear with me.md`). Recommend a default path in the `books/` folder.

### Step 5: Render and Publish
1. Call the **`render`** tool. Pass the selected format and destination path. For `"pdf"`, also pass the collected print settings parameters: `trim_width`, `trim_height`, `bleed`, `gutter`, `outside_margin`, `top_margin`, `bottom_margin`.
2. Confirm the successful creation of the file and provide its absolute path to the user.
3. Inform the user that the rendering parameters have been stored as the project defaults in the `Prompt Directives` document notes.

---

## 🛠️ MCP Tool Reference for Publishing

Use these tools to run the sequence:

### 1. `get_book_outline`
* **Description**: Returns the binder outline hierarchy.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the target book project.

### 2. `read_scene`
* **Description**: Reads the text content, notes, and synopsis of a binder document.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the target book project.
  * `uuid` (string, required): UUID of the `Prompt Directives` document.

### 3. `write_scene`
* **Description**: Writes updated text content, notes, or synopsis back to a binder document.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the target book project.
  * `uuid` (string, required): UUID of the `Prompt Directives` document.
  * `notes` (string, optional): The updated notes text containing the revised metadata table.

### 4. `render`
* **Description**: Compiles and packages the manuscript into a published ebook (ePub), print-ready PDF, or a compiled Markdown file.
* **Parameters**:
  * `project_path` (string, required): Absolute path to the target book project.
  * `output_path` (string, required): Destination file path for the rendered file.
  * `format` (string, optional): The target format (`"amazon"`, `"markdown"`, or `"pdf"`).
  * `trim_width` (number, optional): Trim width in inches.
  * `trim_height` (number, optional): Trim height in inches.
  * `bleed` (boolean, optional): Set to true if background elements bleed.
  * `gutter` (number, optional): Gutter/inside margin in inches.
  * `outside_margin` (number, optional): Outside margin in inches.
  * `top_margin` (number, optional): Top margin in inches.
  * `bottom_margin` (number, optional): Bottom margin in inches.
