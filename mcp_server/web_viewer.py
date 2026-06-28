import json
import os
import threading
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __name__ == "__main__" and not __package__:
    import os
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, os.path.dirname(script_dir))
    __package__ = "mcp_server"

from mcp_server.engine.book_engine import get_book_db
from mcp_server.prompt_loader import load_prompt

# Global reference to the server instance to support stopping
active_server = None
active_server_thread = None

# Base HTML page template served at GET /
# Helper to dynamically read the standalone HTML template from disk
def load_html_template() -> str:
    """Loads the web_viewer.html template, resolving the path relative to this file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "engine", "templates", "web_viewer.html")
    
    # Safety fallback if run in a different context/workspace structure
    if not os.path.exists(template_path):
        template_path = os.path.join("mcp_server", "engine", "templates", "web_viewer.html")
        
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

class HomerHTTPServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default stderr logging to keep standard terminal output readable
        pass

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                html_content = load_html_template()
                self.wfile.write(html_content.encode("utf-8"))
            except Exception as e:
                err_msg = f"<h1>Internal Server Error</h1><p>Could not load HTML template: {e}</p>"
                self.wfile.write(err_msg.encode("utf-8"))
            return

        elif path == "/api/books":
            try:
                from mcp_server.server import list_books
                search_path = query.get("search_path", [None])[0]
                res = list_books(search_path=search_path)
                raw_text = res["content"][0]["text"]
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(raw_text.encode("utf-8"))
            except Exception as e:
                self.send_error_json(str(e))
            return

        elif path == "/api/outline":
            project_path = query.get("project_path", [""])[0]
            if not project_path:
                self.send_error_json("Missing 'project_path' query parameter")
                return
            
            try:
                db = get_book_db(project_path)
                outline = db.get_outline()
                import dataclasses
                outline_dicts = [dataclasses.asdict(node) for node in outline]
                self.send_json(outline_dicts)
            except Exception as e:
                self.send_error_json(str(e))
            return

        elif path == "/api/scene":
            project_path = query.get("project_path", [""])[0]
            uuid = query.get("uuid", [""])[0]
            
            if not project_path or not uuid:
                self.send_error_json("Missing 'project_path' or 'uuid' query parameters")
                return

            try:
                from mcp_server.engine.book_classes import BinderNode
                from mcp_server.readability import compute_readability_metrics
                db = get_book_db(project_path)
                scene_data = db.read_scene(uuid)
                text = scene_data.text
                synopsis = scene_data.synopsis
                
                # Resolve details from binder outline
                scene_title = "Scene"
                node_type = "Text"
                children_data = []
                try:
                    outline = db.get_outline()
                    
                    def find_node_in_nodes(nodes: list[BinderNode], target_uuid: str) -> BinderNode | None:
                        for n in nodes:
                            if n.uuid == target_uuid:
                                return n
                            res = find_node_in_nodes(n.children, target_uuid)
                            if res:
                                return res
                        return None
                        
                    found_node = find_node_in_nodes(outline, uuid)
                    if found_node:
                        scene_title = found_node.title
                        node_type = found_node.type
                        if node_type == "Image":
                            payload = {
                                "title": scene_title,
                                "type": node_type,
                                "text": "",
                                "synopsis": synopsis,
                                "metrics": {
                                    "total_words": 0,
                                    "reading_time_mins": 0,
                                    "flesch_reading_ease": 0.0,
                                    "flesch_grade_level": "N/A",
                                    "grade_level": "N/A"
                                },
                                "children": []
                            }
                            self.send_json(payload)
                            return
                        
                        # If the node is a folder, gather children synopsis & details
                        if node_type in ("Folder", "DraftFolder", "ResearchFolder"):
                            import re
                            
                            compile_status_map = {}
                            def build_compile_map(nodes: list[BinderNode]):
                                for n in nodes:
                                    compile_status_map[n.uuid] = n.include_in_compile
                                    build_compile_map(n.children)
                            build_compile_map(outline)
 
                            # Helper for recursive text gathering
                            def get_all_text_recursively(node: BinderNode):
                                t_list = []
                                n_type = node.type
                                if n_type == "Text":
                                    # Only include in parent's scorecard if compile status is True
                                    if compile_status_map.get(node.uuid, True):
                                        c_files = db.read_scene(node.uuid)
                                        node_text = c_files.text
                                        if node_text:
                                            t_list.append(node_text)
                                for child in node.children:
                                    t_list.extend(get_all_text_recursively(child))
                                return t_list
 
                            for child in found_node.children:
                                child_uuid = child.uuid
                                child_files = db.read_scene(child_uuid)
                                child_type = child.type
                                
                                # Calculate word count for this child
                                if child_type in ("Folder", "DraftFolder", "ResearchFolder"):
                                    child_all_texts = get_all_text_recursively(child)
                                    child_combined_text = "\n\n".join(child_all_texts)
                                    child_cleaned = re.sub(r'<[^>]*>', '', child_combined_text)
                                    child_words = len(re.findall(r"\b[a-zA-Z']+\b", child_cleaned))
                                
                                else:
                                    child_text = child_files.text
                                    child_cleaned = re.sub(r'<[^>]*>', '', child_text)
                                    child_words = len(re.findall(r"\b[a-zA-Z']+\b", child_cleaned))
                                    
                                child_include = compile_status_map.get(child_uuid, True)
                                children_data.append({
                                    "uuid": child_uuid,
                                    "title": child.title,
                                    "type": child_type,
                                    "synopsis": child_files.synopsis,
                                    "word_count": child_words,
                                    "include_in_compile": child_include
                                })
                            
                            all_texts = get_all_text_recursively(found_node)
                            text = "\n\n".join(all_texts)
                except Exception:
                    pass


                # Compute readability scorecard locally
                metrics = compute_readability_metrics(text)
                
                payload = {
                    "title": scene_title,
                    "type": node_type,
                    "text": text,
                    "synopsis": synopsis,
                    "metrics": metrics,
                    "children": children_data
                }
                self.send_json(payload)
            except Exception as e:
                self.send_error_json(str(e))
            return

        elif path == "/api/image":
            project_path = query.get("project_path", [""])[0]
            uuid = query.get("uuid", [""])[0]
            if not project_path or not uuid:
                self.send_error_json("Missing 'project_path' or 'uuid' query parameters")
                return
            try:
                db = get_book_db(project_path)
                image_bytes, mime_type = db.read_image_bytes(uuid)
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(image_bytes)))
                self.end_headers()
                self.wfile.write(image_bytes)
            except Exception as e:
                self.send_error_json(str(e))
            return

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            params = json.loads(body)
        except Exception:
            self.send_error_json("Invalid JSON payload")
            return

        if path == "/api/scorecard":
            text = params.get("text", "")
            try:
                from mcp_server.readability import compute_readability_metrics
                metrics = compute_readability_metrics(text)
                self.send_json({"metrics": metrics})
            except Exception as e:
                self.send_error_json(str(e))
            return

        project_path = params.get("project_path")
        scene_uuid = params.get("scene_uuid")

        if not project_path or not scene_uuid:
            self.send_error_json("Missing required fields: project_path, scene_uuid")
            return

        # 1. Enforce process closed guardrail
        from mcp_server.server import ensure_safe_to_write
        try:
            ensure_safe_to_write(project_path)
        except Exception as e:
            self.send_error_json(str(e))
            return

        if path == "/api/action":
            action = params.get("action")
            selected_text = params.get("selected_text", "").strip()
            instruction = params.get("instruction", "").strip()

            if not action or not selected_text:
                self.send_error_json("Missing required fields: action, selected_text")
                return

            try:
                db = get_book_db(project_path)
                scene_data = db.read_scene(scene_uuid)
                current_text = scene_data.text

                if selected_text not in current_text:
                    self.send_error_json(f"Selected text snippet not found in draft content: '{selected_text[:40]}...'")
                    return

                # Invoke LLM for polish
                from mcp_server.server import (
                    call_ai_model,
                    get_project_genre_benchmarks,
                    get_project_model_setting,
                )
                model_string = get_project_model_setting(project_path, task_type="drafting")
                benchmarks = get_project_genre_benchmarks(project_path)

                # Determine specific system and user prompt based on action
                if action == "sensory":
                    system_prompt = load_prompt("web_sensory_system.txt")
                    user_prompt = (
                        load_prompt("web_sensory_user.txt")
                        .replace("{benchmarks}", json.dumps(benchmarks))
                        .replace("{selected_text}", selected_text)
                        .replace("{instruction}", instruction)
                    )
                elif action == "rewrite":
                    system_prompt = load_prompt("web_rewrite_system.txt")
                    user_prompt = (
                        load_prompt("web_rewrite_user.txt")
                        .replace("{benchmarks}", json.dumps(benchmarks))
                        .replace("{selected_text}", selected_text)
                        .replace("{instruction}", instruction)
                    )
                elif action == "expand":
                    system_prompt = load_prompt("web_expand_system.txt")
                    user_prompt = (
                        load_prompt("web_expand_user.txt")
                        .replace("{benchmarks}", json.dumps(benchmarks))
                        .replace("{selected_text}", selected_text)
                        .replace("{instruction}", instruction)
                    )
                else:
                    self.send_error_json(f"Unknown action type: {action}")
                    return

                # Execute LLM Call
                replacement_text = call_ai_model(system_prompt, user_prompt, model_string, project_path).strip()

                if not replacement_text:
                    self.send_error_json("AI returned empty replacement text.")
                    return

                # Clean/Sanitize quotes if they were added automatically by LLM
                replacement_text = self.clean_llm_quotes(replacement_text, selected_text)

                # Patch draft content
                updated_text = current_text.replace(selected_text, replacement_text, 1)
                db.write_scene(scene_uuid, text=updated_text)

                self.send_json({
                    "status": "success",
                    "action": action,
                    "replaced": selected_text,
                    "replacement": replacement_text
                })

            except Exception as e:
                self.send_error_json(str(e) + "\n" + traceback.format_exc())
            return

        elif path == "/api/snapshot":
            description = params.get("description", "Manual Web Checkpoint").strip()
            try:
                db = get_book_db(project_path)
                success = db.create_scene_snapshot(scene_uuid, description)
                if success:
                    self.send_json({"status": "success"})
                else:
                    self.send_error_json("Failed to create snapshot (check if file exists).")
            except Exception as e:
                self.send_error_json(str(e) + "\n" + traceback.format_exc())
            return

        elif path == "/api/undo":
            try:
                db = get_book_db(project_path)
                res = db.revert_scene_to_last_snapshot(scene_uuid)
                self.send_json(res)
            except Exception as e:
                self.send_error_json(str(e))
            return

        elif path == "/api/save":
            text = params.get("text")
            synopsis = params.get("synopsis")
            title = params.get("title")
            children = params.get("children")
            
            try:
                db = get_book_db(project_path)
                
                # Save the active node itself (always text and/or synopsis) if provided
                if text is not None or synopsis is not None:
                    db.write_scene(scene_uuid, text=text, synopsis=synopsis)
                
                # If a new title is provided for the active node
                if title is not None:
                    db.update_binder_item_meta(scene_uuid, title=title)
                
                # If there are children updates (like titles or synopses for folder child scenes)
                if children:
                    for child in children:
                        c_uuid = child.get("uuid")
                        if not c_uuid:
                            continue
                        c_title = child.get("title")
                        c_synopsis = child.get("synopsis")
                        
                        if c_title is not None:
                            db.update_binder_item_meta(c_uuid, title=c_title)
                        if c_synopsis is not None:
                            db.write_scene(c_uuid, synopsis=c_synopsis)
                
                self.send_json({"status": "success"})
            except Exception as e:
                self.send_error_json(str(e))
            return

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def clean_llm_quotes(self, replacement_text: str, original_text: str) -> str:
        replacement_text = replacement_text.strip()
        quotes = [('"', '"'), ("'", "'"), ('“', '”'), ('‘', '’')]
        for q_start, q_end in quotes:
            if replacement_text.startswith(q_start) and replacement_text.endswith(q_end):
                if not (original_text.startswith(q_start) and original_text.endswith(q_end)):
                    replacement_text = replacement_text[1:-1].strip()
                    break
        return replacement_text

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_json(self, message):
        self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))


def start_server_background(port: int = 8080) -> str:
    """Starts the ThreadingHTTPServer on a background thread if it is not already running."""
    global active_server, active_server_thread
    if active_server is not None:
        return f"Web viewer is already running on http://localhost:{active_server.server_port}"
        
    try:
        active_server = ThreadingHTTPServer(('localhost', port), HomerHTTPServer)
        active_server_thread = threading.Thread(target=active_server.serve_forever, daemon=True)
        active_server_thread.start()
        return f"Successfully started Live Web Viewer at http://localhost:{port}"
    except OSError as e:
        import errno
        if e.errno == errno.EADDRINUSE:
            return f"Web viewer is already active on port {port} (address already in use)."
        return f"Error starting background server on port {port}: {e}"
    except Exception as e:
        # Fall back to trying a clean port or report error
        return f"Error starting background server on port {port}: {e}"

def stop_server_background() -> str:
    """Stops the active ThreadingHTTPServer if running."""
    global active_server, active_server_thread
    if active_server is None:
        return "Web viewer server is not running."
        
    try:
        active_server.shutdown()
        active_server.server_close()
        active_server = None
        active_server_thread = None
        return "Successfully stopped Live Web Viewer server."
    except Exception as e:
        return f"Error stopping background server: {e}"

def get_server_status() -> dict:
    """Returns the current operational status of the server."""
    if active_server is not None:
        return {
            "status": "running",
            "port": active_server.server_port,
            "url": f"http://localhost:{active_server.server_port}"
        }
    return {"status": "stopped"}

if __name__ == "__main__":
    import sys
    port = 8090
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
            
    print(f"Starting standalone Homer Web Viewer on port {port}...")
    try:
        server = ThreadingHTTPServer(('localhost', port), HomerHTTPServer)
        print(f"Live Web Viewer running at http://localhost:{port}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        sys.exit(0)
    except OSError as e:
        import errno
        if e.errno == errno.EADDRINUSE:
            print(f"Port {port} is already in use. Assuming server is already running.")
            sys.exit(0)
        else:
            print(f"Error starting server: {e}")
            sys.exit(1)

