from typing import Any, Dict, List
import os
from flask import Flask, jsonify, request

from llm import answer_question


app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    # Minimal CORS for local Next.js development.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/test", methods=["POST"])
def test_post_method() :
    print("post method reached")
    payload = request.get_json()
    question = payload.get("question")
    
    print(question)
    
    return jsonify({
        "request" : question
    })

@app.route("/query", methods=["POST", "OPTIONS"])
def query_endpoint():
    print("QUERY API hitted")
    if request.method == "OPTIONS":
        return ("", 204)

    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return jsonify({"error": "Missing required field: question"}), 400

    try:
        response_payload = answer_question(question)
    except Exception as e:
        # Avoid leaking internal stack traces to clients.
        return jsonify({"error": "Failed to process query", "details": str(e)}), 500

    return jsonify(response_payload)


@app.route("/graph", methods=["GET"])
def graph_endpoint():
    print("hitting /graph api")
    try:
        from graph import get_graph

        return jsonify(get_graph())
    except ModuleNotFoundError:
        return jsonify({"nodes": [], "edges": []})
    except Exception as e:
        return jsonify({"nodes": [], "edges": [], "error": str(e)}), 500


@app.route("/expand/<node_id>", methods=["GET"])
def expand_endpoint(node_id: str):
    try:
        from graph import get_neighbors

        return jsonify(get_neighbors(node_id))
    except ModuleNotFoundError:
        return jsonify({"neighbors": []})
    except Exception as e:
        return jsonify({"neighbors": [], "error": str(e)}), 500


if __name__ == "__main__":
    # For Next.js dev: frontend calls http://localhost:5000 by default.
    app.run(host="0.0.0.0", port=5000, debug=False)

