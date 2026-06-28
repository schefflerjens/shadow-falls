---
name: homer-continuity-and-copy-edit
description: "Continuity Bible generation and copyedit audit workflow for Scrivener novels. Generates a master Continuity Bible from the manuscript, runs a mechanical/style audit against it, then triages and implements corrections using MCP tools. Covers bulk editing, regex patching, and batch patchset operations."
---

# Continuity & Copyedit Skill (`homer-continuity-and-copy-edit`)

This skill coordinates the micro-level editing pass for a structurally finalized Scrivener manuscript. It runs the Continuity Bible generator and the Copyedit Audit tools, then uses bulk editing capabilities to efficiently apply corrections across the entire project.

---

## 🚫 Critical Guardrail: Tool Delegation & Sequence

> [!CRITICAL]
> **Run the Continuity Bible BEFORE the Copyedit Audit.**
> The audit cross-references against the Bible. If the Bible hasn't been generated first, the audit will produce trivial or contradictory suggestions.

> [!CRITICAL]
> **NEVER run copyedit or continuity tools on a manuscript that hasn't passed through macro-structural editing first.**
> Editing sentences that might later be cut or restructured wastes time. The `run_copyedit_audit` tool should warn if the manuscript hasn't been structurally finalized.

> [!CRITICAL]
> **Always use `dry_run: true` first when testing regex patterns.**
> A bad regex pattern can corrupt dozens of text references across the entire manuscript in a single operation. Always preview before applying.

> [!CRITICAL]
> **NEVER access, read, or write scene files via the local filesystem (Bash, Python, etc.).**
> All manuscript reading must use `read_scene` and all writing must use MCP edit tools. Bypassing MCP breaks snapshot safety and binder integrity.

---

## 📋 The Workflow

### Step 1: Generate the Continuity Bible

1. Run `homer-scrivener_generate_continuity_bible` with the project path.
2. Parameters: `project_path` (required)

3. **Locating and Reading the Deliverables:**
   - The tool saves two deliverables inside the project binder under the `Notes/Editor` folder (prefixed by the project name):
     - **Continuity Bible (JSON)** (`_Continuity_Bible.json`) — Structured data for machine processing.
     - **Continuity Bible (Markdown)** (`_Continuity_Bible.md`) — Human-readable version with all characters, settings, invented terminology, timeline entries, and — most importantly — flagged contradictions.
   - To inspect these deliverables, call `get_book_outline` to locate the folder named `"Notes"` and the subfolder named `"Editor"`.
   - Within `"Notes/Editor"`, find the node UUID corresponding to the desired Bible file.
   - Retrieve its content strictly by calling `read_scene` with the target node's `uuid`. Do not attempt to read from the local filesystem.

4. **Interpret the Bible's findings:**
   - The Bible automatically extracts character names, physical descriptions, locations, invented terminology, and a master timeline from every scene.
   - It **flags contradictions** between scenes (e.g., "Achilles' isolation: stated as both 'twenty years' and '4,011 days'"). These are marked with ⚠️.
   - Each contradiction includes the scene UUIDs where it occurs, making fixes easy to locate.

5. **Triage contradictions with the author:**
   - Present each flagged contradiction to the author.
   - For lore decisions (e.g., "four years ago" vs. "seven years ago" for Sarah's death), ask the author for the correct answer.
   - For numerical errors (e.g., "4,011 days" is only ~11 years, but the text says "twenty years"), decide on the correct number with the author.

### Step 2: Apply Continuity Fixes

Use the bulk editing tools to apply fixes across multiple scenes efficiently:

**Good regex example — target times with care:**
```
pattern: "(eleven|ten|nine|eight|seven|six|five|four|three|two|one) o'clock"
replacement: "\1:00"
```
This is safe because "o'clock" is an unambiguous pattern.

**Bad regex example — DON'T do this:**
```
pattern: "(ten|nine|eight|seven|six|five|four|three|two|one)\s+(thirty|forty|fifty|twenty)"
replacement: "TIME_PLACEHOLDER"
```
Why this is bad:
- The regex matches words that happen to look like times but aren't (e.g., "one twenty" in "one twenty-dollar bill")
- The replacement doesn't actually convert the time to a numeral — it replaces it with a placeholder
- There's no fallback or rollback for bad regex patterns (rely on snapshots)

**Better approach for time conversion** — use `apply_patchset` with exact matches:
```
patches: [
  { "target_text": "seven forty-two in the morning", "replacement_text": "7:42 a.m." },
  { "target_text": "ten twenty-three", "replacement_text": "10:23" },
]
```
This is safer because each patch is an exact match and won't accidentally modify unintended text.

**For simple bulk fixes, use `bulk_patch_scenes`:**
```
bulk_patch_scenes(
  target_text="four thousand and eleven",
  replacement_text="seven thousand, three hundred and twenty-one",
  scene_uuids=["UUID1", "UUID2", ...]  # omit to apply to all
)
```

### Step 3: Run the Copyedit Audit

1. Run `homer-scrivener_run_copyedit_audit` with:
   - `project_path` (required)
   - `style_guide` (required) — e.g., "Chicago Manual of Style"
   - `orthography` (required) — "US" or "UK"

2. The tool saves two deliverables inside the project binder under the `Notes/Editor` folder (prefixed by the project name):
   - **Copyedit Audit (JSON)** (`_Copyedit_Audit.json`) — Structured suggestions with diff-formatted changes.
   - **Copyedit Audit Report (Markdown)** (`_Copyedit_Audit.md`) — Human-readable version organized by scene.

3. **Locating and Reading the Deliverables:**
   - Call `get_book_outline` to locate the folder named `"Notes"` and the subfolder named `"Editor"`.
   - Within `"Notes/Editor"`, locate the nodes corresponding to the desired deliverables.
   - Retrieve their text content strictly by calling `read_scene` with the target node's `uuid`. Do not attempt to read from the local filesystem.

3. **Categorize the suggestions:**
   - **Mechanical Errors** — Typos, punctuation, missing words, repeated words, formatting errors.
   - **Continuity Issues** — Contradictions between Bible and text (already partially caught in Step 1).
   - **Timeline/Plausibility Errors** — Chronological impossibilities, travel time mismatches.

4. **Filter out false positives:**
   - The audit enforces style guide rules strictly (e.g., CMOS comma rules, US orthography).
   - Some suggestions are matters of style and voice, not errors. Discuss with the author before applying.
   - Dialogue in a character's voice may intentionally break style rules (e.g., the Toaster's ALL CAPS).

### Step 4: Apply Copyedit Corrections

Group fixes into batches by type:

1. **Real errors first** (typos, repeated words, missing words, timeline mistakes):
   - Use `patch_scene` for individual fixes in specific scenes.
   - Verify each fix after applying.

2. **Then style standardizations** (time format, US/UK orthography, em dash spacing):
   - These affect many scenes and are good candidates for `bulk_patch_scenes` or `apply_patchset`.
   - Each patch is an exact-text match, so there's no risk of unintended changes.

3. **Pattern-based changes** (use `regex_patch_scenes` only when necessary):
   - Only use regex for patterns that are truly consistent (e.g., em dash spacing: `" — "` → `"—"`).
   - **[CRITICAL] Always use `dry_run: true` first.** Review the match count per scene before applying.
   - If matches seem too numerous, use a more specific pattern.
   - Prefer `apply_patchset` with exact-text patches over regex whenever possible.

### Step 5: Verify

After applying changes:
1. Re-run the Continuity Bible to confirm contradictions are resolved.
2. Re-run the Copyedit Audit to confirm priority items are addressed.
3. Spot-check a few scenes to ensure the author's voice wasn't flattened by style standardization.

---

## 🛠️ MCP Tool Reference

| Tool | Purpose | When to Use |
|---|---|---|
| `generate_continuity_bible` | Extract character/location/timeline consistency data | Step 1 |
| `run_copyedit_audit` | Mechanical, grammatical, and style audit | Step 3 |
| `bulk_patch_scenes` | Same exact-text replacement across multiple scenes | Steps 2, 4 |
| `regex_patch_scenes` | Regex-based replacement across multiple scenes | Step 4 (use sparingly) |
| `apply_patchset` | Multiple different replacements in one operation | Step 4 (preferred for multi-fix passes) |
| `patch_scene` | Single exact-text replacement in one scene | Steps 2, 4 (individual fixes) |
| `read_scene` | Verify changes after patching | Step 5 |
| `search_project` | Find all occurrences of a string across the project | Step 5 (verification) |

---

## 🚧 Evolution Notes

- **Snapshot safety:** All bulk editing tools create native Scrivener XML snapshot backups. If a regex pattern causes unintended changes, restore from the snapshot in Scrivener's Inspector → Snapshots tab.
- **Bulk tool output:** The tools return a per-scene summary showing match count and modification status. Use this to verify that the expected number of changes was made.
- **Regex is risky:** A single bad regex can damage dozens of text references across 18 scenes in one operation. Always dry-run first, and prefer exact-text `bulk_patch_scenes` or `apply_patchset` over regex whenever possible.
- **Style vs. substance:** Not every copyedit suggestion needs to be implemented. US orthography in a British-set novel, for example, may be a deliberate choice by the author. Discuss with the author before applying style-only changes.