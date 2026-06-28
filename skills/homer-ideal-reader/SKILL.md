---
name: homer-ideal-reader
description: "Simulates the target audience 'Ideal Reader' persona on a Scrivener manuscript to produce an Editorial Letter and context-specific inline comments. Captures the persona setup, tool invocation, feedback triage, and implementation workflow."
---

# Ideal Reader Simulation Skill (`homer-ideal-reader`)

This skill coordinates the Ideal Reader simulation loop: defining a target audience persona, running the simulation tool, interpreting the output, and triaging actionable feedback with the author.

---

## 🚫 Critical Guardrail: Tool Delegation

> [!CRITICAL]
> **Do NOT make changes to the manuscript based on the Ideal Reader feedback without author approval.**
> The simulation produces subjective feedback from a hypothetical reader. Every suggested change must be discussed with the author before execution.

> [!CRITICAL]
> **NEVER write custom Python scripts or edit `.scriv` package files directly.**
> All edits must go through MCP tools (`patch_scene`, `write_scene`, `insert_into_scene`, `create_binder_item`, `delete_binder_item`).

> [!CRITICAL]
> **NEVER access, read, or write scene files via the local filesystem (Bash, Python, etc.).**
> All manuscript reading must use `read_scene` and all writing must use MCP edit tools. Bypassing MCP breaks snapshot safety and binder integrity.

---

## 🔄 The Ideal Reader Workflow

### Step 1: Define the Ideal Reader Persona

Before running the tool, establish the target reader profile. This can be done in two ways:

1. **Create a binder document** titled `Ideal Reader` in the `[Agent Workspace]` folder with a detailed persona description
2. **Pass the `persona_profile` parameter** directly to the tool

The persona should include:
- **Demographics:** Age, grade level, reading level
- **Taste:** What kind of stories they love, comparable titles
- **Sensitivity:** What they notice (inconsistencies, emotional authenticity, pacing issues)
- **Expectations:** What they need from this specific book

**Example (Bear Arms, MG ages 8-12):**
```
Name: Maya (age 10)
Grade: Year 5
Loves: Percy Jackson, The Wild Robot, The Bad Guys
Wants: Funny narrator, active kid protagonist, emotional beats that land without being spelled out
Notices: When adults are conveniently absent, when characters act out of character, when the book talks down to her
```

### Step 2: Run the Simulation

1. Call `homer-scrivener_simulate_ideal_reader` with the project path. Optionally pass `persona_profile` and `author_concerns` to override or supplement the binder document.

2. The tool saves three deliverables inside the project binder under the `Notes/Editor` folder (prefixed by the project name):
   - **Editorial Letter** (`_Ideal_Reader_Editorial_Letter.md`) — A detailed letter from the Ideal Reader persona discussing what worked, what didn't, and what they'd change. This is the primary deliverable — read it first.
   - **Inline Comments (JSON)** (`_Ideal_Reader_Inline_Comments.json`) — Structured comments keyed to specific scene UUIDs with anchor text/quotes, categorized as `Positive Reinforcement` or `Developmental Issue`.
   - **Inline Comments (Markdown)** (`_Ideal_Reader_Inline_Comments.md`) — A human-readable version of the inline comments with scene titles and full quote context.

3. **Locating and Reading the Deliverables:**
   - Call `get_book_outline` to locate the folder named `"Notes"` and the subfolder named `"Editor"`.
   - Within `"Notes/Editor"`, locate the nodes corresponding to the desired deliverables.
   - Retrieve their text content strictly by calling `read_scene` with the target node's `uuid`. Do not attempt to read from the local filesystem.

### Step 3: Interpret the Output

Read the Editorial Letter first. It provides the big-picture reader experience. Then review the inline comments.

The inline comments come in two categories:
- **Positive Reinforcement** — What the Ideal Reader loved. These confirm your strengths and should be preserved in any revision.
- **Developmental Issue** — Specific passages the Ideal Reader flagged as needing attention. Each includes the scene UUID, anchor text, and a suggestion for improvement.

Categorize each developmental issue:
- **Critical** — Blocks reader enjoyment or comprehension (high priority)
- **Polishing** — Would improve the experience but isn't broken (medium priority)
- **Debatable** — A matter of taste; discuss with the author (low priority)
- **Erroneous** — The tool misunderstood something; discard

### Step 4: Triage with the Author

Present findings in a structured, conversational way:

1. **What the Ideal Reader loved** — Lead with strengths. This builds confidence and shows the tool's perspective is grounded.
2. **What the Ideal Reader flagged** — Present each developmental issue with:
   - The specific scene and anchor text
   - Why it matters to the reader's experience
   - The suggested revision (in the Ideal Reader's own words)
   - Your assessment: critical, polishing, or debatable
3. **Discuss each item** — Ask the author for their perspective. Some flagged items will be intentional author choices (e.g., leaving Leo's fate open as a sequel hook). Others will be genuine gaps worth fixing.
4. **Agree on action** — For each item the author wants to address, decide on the fix approach and the right MCP tool.

### Step 5: Implement Changes

For each agreed change, identify the right tool:
- `patch_scene` — Targeted text changes
- `insert_into_scene` — Add context at a specific point
- `write_scene` — Full scene replacement (sparingly)
- `generate_draft_beat` — Draft new scenes

Execute, verify, and report back.

---

## 🛠️ MCP Tool Reference

| Tool | Purpose | When to Use |
|---|---|---|
| `simulate_ideal_reader` | Run the simulation | Step 2 |
| `get_book_outline` | View binder hierarchy | Finding scene UUIDs |
| `read_scene` | Read scene text before/after edits | Verification |
| `patch_scene` | Targeted text changes | Most fixes |
| `insert_into_scene` | Add prose at specific anchor | Adding context |
| `write_scene` | Full scene replacement | Major rewrites (rare) |
| `generate_draft_beat` | Draft new scenes | New content |

---

## 🚧 Evolution Notes

This skill is designed to evolve as the Ideal Reader tool matures. Observations from practical use:

- **Tool reliability:** The tool may produce empty output on the first attempt due to generation pipeline issues. If the Editorial Letter and Inline Comments files are empty (all `[]`), flag it to the author for the coding agent to investigate. The tool often works on retry.
- **Persona depth:** The more specific the persona, the more useful the feedback. Generic personas ("a 10-year-old") produce generic feedback. Include comparable titles, reading habits, and sensitivity flags. The persona document in the binder is read automatically when no `persona_profile` parameter is passed.
- **Author concerns:** Use the `author_concerns` parameter to direct the Ideal Reader's attention to specific questions (e.g., "Does the pacing in Part Two feel slow?"). This produces more targeted feedback on known weak spots.
- **Inline comment format:** Comments are keyed to scene UUIDs, not line numbers. The anchor text is a quote from the scene. Use the UUID to look up the scene with `read_scene` when implementing changes.
- **Frequency:** Run no more than once per major revision. The Ideal Reader feedback is most valuable after a full draft is complete and macro-structural issues have been resolved.
- **Not every flag needs action:** The Ideal Reader's suggestions are subjective. Some flagged items will be deliberate author choices (e.g., unresolved sequel hooks). Discuss each item with the author before implementing.