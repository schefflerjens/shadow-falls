from mcp_server.mcp_server import server


@server.register_tool(name='start_web_viewer', description='Starts the HTML background web server to render and polish chapter drafts in real-time in your web browser.', schema={'type': 'object', 'properties': {'port': {'type': 'integer', 'description': 'Port number to start the server on. Defaults to 8080.', 'default': 8080}}})
def start_web_viewer_tool(port: int=8080) -> dict:
    try:
        from mcp_server.web_viewer import start_server_background
        res = start_server_background(port)
        return {'content': [{'type': 'text', 'text': res}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}
