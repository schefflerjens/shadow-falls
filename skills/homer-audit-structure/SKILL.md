---
name: homer-audit-structure
description: "Macro-structural developmental editing workflow for Scrivener novels. Runs the SAC analysis tool, interprets the audit output, triages open issues with the author, and implements feedback using MCP tools. Designed to evolve as new tools are added to the MCP server."
---

# Macro-Structural Audit Skill (`homer-audit-structure`)

This skill coordinates the developmental editing loop for completed or partially completed Scrivener manuscripts. It runs the macro-structural analysis tool, surfaces the findings to the author in a digestible way, and walks through triaging and implementing the feedback using available MCP tools.

Rather than acting as an editor who makes changes autonomously, this skill positions the agent as a **coordinator** — running diagnostics, surfacing insights, and executing the author's decisions with MCP tools.

---

## 🚫 Critical Guardrail: Tool Delegation

> [!CRITICAL]
> **Do NOT rewrite, restructure, or delete manuscript content without author approval.**
> The macro-structural audit surfaces problems and opportunities. Every change must be discussed with the author before execution.

> [!CRITICAL]
> **NEVER write custom Python scripts or edit `.scriv` package files directly.**
> All edits must go through MCP tools (`patch_scene`, `write_scene`, `insert_into_scene`, `create_binder_item`, `delete_binder_item`) which handle XML/RTF safety and snapshot backups.

> [!CRITICAL]
> **NEVER access, read, or write scene files via the local filesystem (Bash, Python, etc.).**
> All manuscript reading must use `read_scene` and all writing must use MCP edit tools. Bypassing MCP breaks snapshot safety and binder integrity.

> [!IMPORTANT]
> **The `analyze_macro_structure` tool is computationally heavy and may take up to 15 minutes.**
> The tool requires an extended MCP timeout. Ensure OpenCode's configuration (`~/.config/opencode/opencode.jsonc`) has `"experimental": { "mcp_timeout": 900000 }` and the `homer-scrivener` server entry has `"timeout": 900000`. Do not cancel execution while the tool is running — the files will be generated even if the client shows a timeout error.

---

## 🔄 The Editing Workflow

### Step 1: Run the Audit

1. Run `homer-scrivener_analyze_macro_structure` with the target project path.
   - Parameters: `project_path` (absolute path to project package)
   - Optional: `chapter_outline_path`, `synopsis_path`, `author_concerns` for focus guidance

2. The tool saves three deliverables inside the project binder under the `Notes/Editor` folder (with filenames prefixed by the project name):
   - **SAC Database** (`_SAC_Database.json`) — Scene-by-scene assessment with writer intent, thematic takeaways, timeline data, and subplot tracking. May contain `JSON Parse Error` entries for scenes the tool could not parse — flag these to the author.
   - **Editorial Assessment** (`_Macro_Structural_Assessment.md`) — High-level narrative throughline analysis, plot holes and structural gaps, pacing and redundancy evaluation, subplot resolution tracking.
   - **Open Issues List** (`_Open_Issues_List.md`) — Actionable items grouped into:
     - Unanswered Narrative Questions
     - Continuity Errors & Timeline Gaps
     - Research Gaps & Factual Verification

3. **Locating and Reading the Deliverables:**
   - To inspect these deliverables, call `get_book_outline` to locate the folder named `"Notes"` and the subfolder named `"Editor"`.
   - Within `"Notes/Editor"`, locate the nodes corresponding to the desired deliverables.
   - Retrieve their text content strictly by calling `read_scene` with the target node's `uuid`. Do not attempt to read from the local filesystem.

4. **Interpret the output:**
   - Identify which issues are **critical** (block narrative coherence) vs. **polish** (nice-to-have).
   - Identify which issues have **simple fixes** (a single `patch_scene` call) vs. **complex fixes** (new scenes, restructuring).
   - Cross-reference with known project constraints from `Prompt Directives`, character sheets, and `Craft Brief` documents.

### Step 2: Surface Findings to the Author

Present the findings in a structured, conversational way:

- **Strengths** — What the audit confirms is working well.
- **Critical gaps** — The issues the author should address first.
- **Actionable items** — Present these as a triaged list with:
  - The specific issue
  - The tool(s) available to fix it
  - Whether the fix requires author input (lore decisions) or can be executed immediately
  - Any MCP tool gaps — if the fix requires a tool that doesn't exist yet, flag this clearly

### Step 3: Walk Through Actionable Feedback

For each issue the author wants to address:

1. **Confirm the fix approach** — Discuss how to resolve it. For lore questions (e.g., "Why did Augustus take Mina to the Ironworks?"), ask the author for the answer. For mechanical fixes (e.g., "Weekday is null for scene 1"), propose the solution.

2. **Identify the right tool:**
   - `patch_scene` — Search-and-replace for targeted text changes (author provides exact replacement text, or agent writes it)
   - `insert_into_scene` — Insert AI-generated prose at a specific anchor point using the calibrated writer engine (best for adding context without rewriting)
   - `write_scene` — Full scene replacement (use sparingly — prefer `patch_scene` or `insert_into_scene` for smaller changes)
   - `create_binder_item` / `delete_binder_item` — Structural changes (new scenes, removing stubs)
   - `generate_draft_beat` — Draft new scenes from synopsis

3. **Check for tool gaps.** If the right tool doesn't exist:
   - Name the missing capability
   - Describe what the tool should do (parameters, behavior, constraints)
   - Flag it to the author so they can have their coding agent build it

4. **Execute the fix** using the agreed tool and approach.

5. **Verify the result** — Read the modified scene to confirm the edit is correct.

### Step 4: Track Progress

Maintain a running log of:
- Issues identified from the audit
- Author decisions on each issue
- Which tool was used to fix it
- Whether the fix succeeded or needs iteration
- Any tool gaps discovered during the process

---

## 🛠️ MCP Tool Reference

| Tool | Purpose | When to Use |
|---|---|---|
| `analyze_macro_structure` | Run the SAC audit | Step 1 |
| `compile_manuscript` | Get full manuscript text | Before the audit, or to read the current state |
| `get_book_outline` | View binder hierarchy | Finding scene UUIDs, checking structure |
| `read_scene` | Read scene text, notes, synopsis | Before any edit, verify after edit |
| `patch_scene` | Search-and-replace in a scene | Targeted text changes |
| `insert_into_scene` | Insert AI-generated prose after an anchor | Adding context, dialogue, or description at a specific point |
| `write_scene` | Full scene replacement | Major rewrites (use sparingly) |
| `generate_draft_beat` | Draft new scenes | New content creation |
| `create_binder_item` | Create new scenes or folders | Structural changes |
| `delete_binder_item` | Delete scenes or folders | Removing old content |
| `get_scene_readability_metrics` | Programmatic readability check | Verification after editing |

---

## 📋 Common Audit Findings & Responses

| Finding | Typical Fix | MCP Tool |
|---|---|---|
| Missing inciting incident motivation | Add dialogue/context to early scene | `insert_into_scene` |
| Timeline / weekday gaps | Add timestamp lines to scene text | `patch_scene` |
| Character lore contradiction | Fix the offending line(s) | `patch_scene` |
| Unresolved subplot (minor) | Add resolution lines to existing scene | `insert_into_scene` or `patch_scene` |
| Unresolved subplot (major) | Draft new scene(s) | `create_binder_item` + `generate_draft_beat` |
| Redundant scene | Remove or consolidate | `delete_binder_item` |
| JSON Parse Error in SAC | Scene content doesn't fit tool's expected format — flag to author | Read the scene manually and assess |
| Tool gap identified | Name the gap, spec the tool, flag to author | Author's coding agent |

---

## 🚧 Evolution Notes

This skill is designed to evolve as the MCP server grows. Known gaps and planned additions:

- Batch operations: editing multiple scenes at once (e.g., timeline cleanup across 9 scenes)
- Cross-scene consistency checks: flagging character trait contradictions automatically
- Thematic drift detection: tracking whether a scene's executed content matches its intended writer intent
- Subplot thread tracking: visualizing whether each subplot has introduction, development, and resolution scenes

As new tools are added, update the MCP Tool Reference table and the Audit Findings table accordingly.