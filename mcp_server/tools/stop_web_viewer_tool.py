from mcp_server.mcp_server import server


@server.register_tool(name='stop_web_viewer', description='Shuts down the active background HTML web server.', schema={'type': 'object', 'properties': {}})
def stop_web_viewer_tool() -> dict:
    try:
        from mcp_server.web_viewer import stop_server_background
        res = stop_server_background()
        return {'content': [{'type': 'text', 'text': res}]}
    except Exception as e:
        return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}
