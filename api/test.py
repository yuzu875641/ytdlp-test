import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests to demonstrate Python calling Node.js"""
        try:
            # Parse query parameters
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Get message from query parameter or use default
            message = query_params.get("message", ["Demo from Python to Node.js!"])[0]

            # Call the Node.js script with the message
            result = subprocess.run(
                ["node", "scripts/test.js", message],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(__file__)),  # Go up to project root
            )

            # Set response headers
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Parse Node.js output
            if result.returncode == 0:
                try:
                    node_output = json.loads(result.stdout)
                    response = {
                        "success": True,
                        "python_info": {
                            "handler": "Python serverless function",
                            "method": "GET",
                            "path": self.path,
                            "query_params": query_params,
                        },
                        "node_js_output": node_output,
                        "demonstration": "Python successfully called Node.js script!",
                    }
                except json.JSONDecodeError:
                    response = {
                        "success": True,
                        "python_info": {
                            "handler": "Python serverless function",
                            "method": "GET",
                            "path": self.path,
                        },
                        "node_js_raw_output": result.stdout,
                        "note": "Node.js output was not JSON",
                    }
            else:
                response = {
                    "success": False,
                    "error": "Node.js script failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                    "return_code": result.returncode,
                }

            # Send JSON response
            self.wfile.write(json.dumps(response, indent=2).encode())

        except Exception as e:
            # Handle any Python errors
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            error_response = {
                "success": False,
                "error": "Python error",
                "message": str(e),
                "type": type(e).__name__,
            }

            self.wfile.write(json.dumps(error_response, indent=2).encode())

    def do_POST(self):
        """Handle POST requests with JSON data"""
        try:
            # Read POST data
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")

            # Parse JSON data
            json_data = {}
            try:
                json_data = json.loads(post_data) if post_data else {}
                message = json_data.get(
                    "message", "POST request from Python to Node.js!"
                )
            except json.JSONDecodeError:
                message = "Invalid JSON in POST request"

            # Call Node.js with the message
            result = subprocess.run(
                ["node", "scripts/test.js", message],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(__file__)),
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            if result.returncode == 0:
                try:
                    node_output = json.loads(result.stdout)
                    response = {
                        "success": True,
                        "method": "POST",
                        "received_data": json_data,
                        "node_js_output": node_output,
                    }
                except json.JSONDecodeError:
                    response = {
                        "success": True,
                        "method": "POST",
                        "node_js_raw_output": result.stdout,
                    }
            else:
                response = {
                    "success": False,
                    "error": "Node.js script failed",
                    "stderr": result.stderr,
                }

            self.wfile.write(json.dumps(response, indent=2).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            error_response = {"success": False, "error": str(e)}

            self.wfile.write(json.dumps(error_response, indent=2).encode())
