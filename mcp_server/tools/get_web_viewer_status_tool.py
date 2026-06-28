import json

from mcp_server.mcp_server import server


@server.register_tool(name='get_web_viewer_status', description='Checks the current status, port, and URL of the Live Web Viewer background server.', schema={'type': 'object', 'properties': {}})
def get_web_viewer_status_tool() -> dict:
    try:
        from mcp_server.web_viewer import get_server_status
        status = get_server_status()
        return {'content': [{'type': 'text', 'text': json.dumps(status, indent=2)}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}
