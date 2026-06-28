import os


def load_prompt(filename: str) -> str:
    """Loads a prompt template from the prompts folder, resolving the path relative to this file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(base_dir, "prompts", filename)
    
    # Safety fallback if run in a different context/workspace structure
    if not os.path.exists(prompt_path):
        prompt_path = os.path.join("mcp_server", "prompts", filename)
        
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()
