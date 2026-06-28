# Streamlined server runner and dynamic tool loader
import importlib
import os

if __name__ == "__main__" and not __package__:
    import os
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, os.path.dirname(script_dir))
    __package__ = "mcp_server"

from mcp_server.mcp_server import server
from mcp_server.server_utils import *

# Dynamically load all tool modules from mcp_server/tools/
tools_dir = os.path.join(os.path.dirname(__file__), "tools")
for file in os.listdir(tools_dir):
    if file.endswith(".py") and file not in ("__init__.py", "utils.py"):
        module_name = f"mcp_server.tools.{file[:-3]}"
        mod = importlib.import_module(module_name)
        for name in dir(mod):
            if not name.startswith("_"):
                globals()[name] = getattr(mod, name)

if __name__ == "__main__":
    server.run()
