# Homer MCP (Collaborative Fiction Writing Server)

Homer MCP is a Model Context Protocol (MCP) server designed to enable collaborative fiction writing, structural editing, and publishing pipelines between humans and AI agents.

Originally developed as a private assistant, this repository serves as the public open-source release of the Homer MCP project.

## Overview

Homer MCP acts as a bridge between LLM writing agents and book project directories (such as Scrivener or GitBook formats). It provides tools for navigating outline hierarchies, drafting scenes, running analytical developmental critiques, and compiling final drafts to Kindle-compliant ebooks.

## Repository Layout

- **[Shadow Falls.gitbook/](Shadow%20Falls.gitbook/)**: An example book project in the `.gitbook` format — a git-friendly, folder-based representation of a book project. It showcases how manuscript outlines, character bibles, location profiles, and story notes are structured for the MCP.
  - 📖 [Read the compiled manuscript](Shadow%20Falls.md)
  - 📱 [Download EPUB](Shadow%20Falls.epub)
- **[engine_deprecated/](engine_deprecated/)**: The original custom Python-based writing assistant, preserved here as historical context only.

**Note on cost:** the MCP uses open router, so you can pick and choose what LLMs should do the writing and the editing. For this book, the writer was Claude Sonnet 4.6 and the editor was Gemini 2.5 Pro. In total, the book cost about 12 USD to produce.

## Key Features

1. **Structured Outline Navigation**: Seamless read/write integration for manuscript chapters, scenes, characters, and places.
2. **Readability Diagnostics**: Analyzes prose for reading level (Flesch-Kincaid Grade Level), sentence length, adverb density, passive voice, and filler words.
3. **Macro-Structural Auditing**: Run developmental editing audits over the entire manuscript to catalog plot beats, timelines, character goals, and thematic developments.
4. **Ideal Reader Simulation**: Simulates specific persona-driven reader perspectives to identify potential pacing, continuity, or emotional resonance issues.
5. **Ebook Publishing**: Direct rendering to standard Kindle-compatible EPUB (`"amazon"` format) with support for hierarchical tables of contents.

## Getting Started

To run the Homer MCP server, connect it to your MCP client (such as Claude Desktop, OpenCode, or other IDE integrations).

### MCP Configuration

Add the server to your `mcp_config.json`:

```json
{
  "mcpServers": {
    "homer": {
      "command": "python",
      "args": ["/path/to/homer/mcp_server/server.py"]
    }
  }
}
```

*For licensing information, see [LICENSE.md](file:///Users/jensscheffler/projects/shadow-falls/LICENSE.md).*
