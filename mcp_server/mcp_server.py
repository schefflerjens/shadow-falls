import json
import sys
import traceback


class MCPServer:
    def __init__(self, name="homer-scrivener", version="1.0.0"):
        self.name = name
        self.version = version
        self.tools = {}

    def register_tool(self, name, description, schema):
        def decorator(func):
            self.tools[name] = {
                "func": func,
                "description": description,
                "schema": schema
            }
            return func
        return decorator

    def run(self):
        sys.stderr.write(f"Homer Scrivener MCP Server started [name={self.name}, version={self.version}]\n")
        sys.stderr.flush()
        
        # Read from sys.stdin line by line
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                tb = traceback.format_exc()
                sys.stderr.write(f"Error handling request: {e}\nTraceback:\n{tb}\n")
                sys.stderr.flush()

    def handle_request(self, req):
        msg_id = req.get("id")
        method = req.get("method")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version
                    }
                },
                "id": msg_id
            }
            
        elif method == "notifications/initialized":
            return None
            
        elif method == "tools/list":
            tools_list = []
            for name, info in self.tools.items():
                tools_list.append({
                    "name": name,
                    "description": info["description"],
                    "inputSchema": info["schema"]
                })
            return {
                "jsonrpc": "2.0",
                "result": {
                    "tools": tools_list
                },
                "id": msg_id
            }
            
        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name not in self.tools:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {tool_name}"
                    },
                    "id": msg_id
                }
                
            try:
                result = self.tools[tool_name]["func"](**arguments)
                if isinstance(result, dict) and "content" in result:
                    return {
                        "jsonrpc": "2.0",
                        "result": result,
                        "id": msg_id
                    }
                
                text_res = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": text_res
                            }
                        ]
                    },
                    "id": msg_id
                }
            except Exception as e:
                tb = traceback.format_exc()
                sys.stderr.write(f"Error executing tool {tool_name}: {tb}\n")
                sys.stderr.flush()
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": f"Execution error in {tool_name}: {str(e)}"
                    },
                    "id": msg_id
                }
                
        elif method in ("resources/list", "resources/templates/list"):
            return {
                "jsonrpc": "2.0",
                "result": {
                    "resources": []
                },
                "id": msg_id
            }
            
        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "prompts": []
                },
                "id": msg_id
            }
            
        # If it's a request we don't know, return method not found
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
                "id": msg_id
            }
        return None


# Instantiate server
server = MCPServer("homer-scrivener", "1.0.0")
