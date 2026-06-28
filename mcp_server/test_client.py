import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def run_integration_test():
    print("==================================================")
    print("Starting Homer MCP Server Integration Test Client")
    print("==================================================")
    
    # 1. Create a temporary directory for book projects
    temp_dir = tempfile.mkdtemp()
    print(f"Created temporary books directory: {temp_dir}")
    # Initialize Git in the temp directory so GitBook projects are valid
    subprocess.run(["git", "init"], cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    dummy_file = os.path.join(temp_dir, "init.txt")
    with open(dummy_file, "w", encoding="utf-8") as f:
        f.write("init")
    subprocess.run(["git", "add", "init.txt"], cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    # 2. Launch the MCP server as a subprocess
    # Run it using the same python interpreter
    server_cmd = [sys.executable, "-m", "mcp_server.server"]
    
    # We set env to make sure PYTHONPATH includes current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    server_proc = subprocess.Popen(
        server_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env
    )
    
    # Simple helper to read log messages from stderr in a non-blocking way
    # (just to make sure server initialized)
    time.sleep(0.5)
    
    # Helper to send a request and read a response
    msg_id = 1
    
    def send_request(method, params=None):
        nonlocal msg_id
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "id": msg_id
        }
        if params is not None:
            req["params"] = params
            
        req_line = json.dumps(req) + "\n"
        # Write to server's stdin
        server_proc.stdin.write(req_line)
        server_proc.stdin.flush()
        
        # Read from server's stdout
        resp_line = server_proc.stdout.readline()
        if not resp_line:
            raise RuntimeError("Server closed connection or crashed.")
            
        resp = json.loads(resp_line)
        msg_id += 1
        return resp

    try:
        # Step 1: Initialize the connection
        print("\n[Step 1] Initializing MCP protocol...")
        init_resp = send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        print("Initialization Response:")
        print(json.dumps(init_resp, indent=2))
        assert "result" in init_resp, "Initialization failed"
        assert init_resp["result"]["serverInfo"]["name"] == "homer-scrivener"
        
        # Send initialized notification (no id, so no response)
        server_proc.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }) + "\n")
        server_proc.stdin.flush()
        print("Initialized notification sent.")

        # Step 2: List tools
        print("\n[Step 2] Listing registered tools...")
        tools_resp = send_request("tools/list")
        tools = tools_resp.get("result", {}).get("tools", [])
        print(f"Found {len(tools)} tools:")
        for t in tools:
            print(f" - {t['name']}: {t['description']}")
        
        tool_names = [t["name"] for t in tools]
        assert "create_new_book" in tool_names
        assert "list_books" in tool_names
        assert "get_book_outline" in tool_names
        assert "read_scene" in tool_names
        assert "write_scene" in tool_names
        assert "create_binder_item" in tool_names
        assert "delete_binder_item" in tool_names
        assert "remove_image_watermark" in tool_names
        
        # Step 3: Create a brand new project
        print("\n[Step 3] Creating a new Scrivener project 'Aeneid'...")
        create_resp = send_request("tools/call", {
            "name": "create_new_book",
            "arguments": {
                "target_dir": temp_dir,
                "book_name": "Aeneid",
                "format": "scrivener"
            }
        })
        print("Create response:")
        print(json.dumps(create_resp, indent=2))
        assert "error" not in create_resp, "Error creating book"
        
        project_path = os.path.join(temp_dir, "Aeneid.scriv")
        assert os.path.exists(project_path), f"Project path does not exist: {project_path}"

        # Step 3b: Create a brand new GitBook project 'Iliad'
        print("\n[Step 3b] Creating a new GitBook project 'Iliad'...")
        create_gb_resp = send_request("tools/call", {
            "name": "create_new_book",
            "arguments": {
                "target_dir": temp_dir,
                "book_name": "Iliad",
                "format": "gitbook"
            }
        })
        print("Create GitBook response:")
        print(json.dumps(create_gb_resp, indent=2))
        assert "error" not in create_gb_resp, "Error creating GitBook"
        
        gb_project_path = os.path.join(temp_dir, "Iliad.gitbook")
        assert os.path.exists(gb_project_path), f"GitBook path does not exist: {gb_project_path}"

        # Step 4: List book projects
        print("\n[Step 4] Listing book projects in the directory...")
        list_resp = send_request("tools/call", {
            "name": "list_books",
            "arguments": {
                "search_path": temp_dir
            }
        })
        print("List books response:")
        books_data = json.loads(list_resp["result"]["content"][0]["text"])
        print(json.dumps(books_data, indent=2))
        assert len(books_data) == 2
        book_names = [b["name"] for b in books_data]
        assert "Aeneid" in book_names
        assert "Iliad" in book_names

        # Step 5: Get outline
        print("\n[Step 5] Getting project binder outline...")
        outline_resp = send_request("tools/call", {
            "name": "get_book_outline",
            "arguments": {
                "project_path": project_path
            }
        })
        print("Outline response:")
        outline_data = json.loads(outline_resp["result"]["content"][0]["text"])
        print(json.dumps(outline_data, indent=2))
        
        # Find Manuscript and trash folders
        manuscript_uuid = None
        for item in outline_data:
            if item["type"] == "DraftFolder":
                manuscript_uuid = item["uuid"]
                break
        assert manuscript_uuid is not None, "Manuscript folder not found in outline"
        print(f"Manuscript folder UUID: {manuscript_uuid}")

        # Step 6: Create scene
        print("\n[Step 6] Creating a new scene 'Fall of Troy' under Manuscript...")
        scene_resp = send_request("tools/call", {
            "name": "create_binder_item",
            "arguments": {
                "project_path": project_path,
                "parent_uuid": manuscript_uuid,
                "title": "Fall of Troy",
                "item_type": "Text"
            }
        })
        print("Create scene response:")
        print(json.dumps(scene_resp, indent=2))
        
        # Parse the new UUID from the return text
        # "Successfully created Text 'Fall of Troy' with UUID <UUID>."
        resp_text = scene_resp["result"]["content"][0]["text"]
        new_uuid = resp_text.split("with UUID ")[1].split(".")[0]
        print(f"New Scene UUID: {new_uuid}")

        # Step 7: Write content to scene
        print("\n[Step 7] Writing story text and synopsis to 'Fall of Troy'...")
        write_resp = send_request("tools/call", {
            "name": "write_scene",
            "arguments": {
                "project_path": project_path,
                "uuid": new_uuid,
                "text": "The wooden horse entered the gates of Troy. Accented: á é í ó ú. Emoji: 🐴.",
                "synopsis": "The Greeks execute their final trick.",
                "notes": "Ensure Laocoon is mentioned."
            }
        })
        print("Write scene response:")
        print(json.dumps(write_resp, indent=2))

        # Step 8: Read content back
        print("\n[Step 8] Reading the scene content back...")
        read_resp = send_request("tools/call", {
            "name": "read_scene",
            "arguments": {
                "project_path": project_path,
                "uuid": new_uuid
            }
        })
        print("Read scene response:")
        scene_data = json.loads(read_resp["result"]["content"][0]["text"])
        print(json.dumps(scene_data, indent=2))
        assert "wooden horse" in scene_data["text"]
        assert "🐴" in scene_data["text"]
        assert "Greeks execute" in scene_data["synopsis"]
        assert "Laocoon" in scene_data["notes"]

        # Step 9: Soft delete
        print("\n[Step 9] Soft deleting the scene...")
        delete_resp = send_request("tools/call", {
            "name": "delete_binder_item",
            "arguments": {
                "project_path": project_path,
                "uuid": new_uuid,
                "hard_delete": False
            }
        })
        print("Delete scene response:")
        print(json.dumps(delete_resp, indent=2))
        
        # Verify it has been moved to Trash
        outline_after_del = send_request("tools/call", {
            "name": "get_book_outline",
            "arguments": {
                "project_path": project_path
            }
        })
        outline_after_del_data = json.loads(outline_after_del["result"]["content"][0]["text"])
        
        trash_item = None
        for item in outline_after_del_data:
            if item["type"] == "TrashFolder":
                trash_item = item
                break
        assert trash_item is not None
        assert len(trash_item["children"]) == 1
        assert trash_item["children"][0]["uuid"] == new_uuid
        print("Verified that deleted scene was successfully soft-deleted to Trash!")

        print("\n==================================================")
        print("ALL INTEGRATION TESTS PASSED TRIUMPHANTLY!")
        print("==================================================")

    finally:
        # Terminate server process
        server_proc.terminate()
        server_proc.wait()
        
        # Cleanup temporary directory
        shutil.rmtree(temp_dir)
        print(f"\nCleaned up temporary books directory: {temp_dir}")

if __name__ == "__main__":
    run_integration_test()
