// lib/api.js
// Matches Flask backend: app.py + graph_builder.py

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

/**
 * GET /api/graph/overview
 * Returns { nodes, edges } in vis.js format:
 *   nodes[i]: { id, label, title, color, type, key, group, ...attrs }
 *   edges[i]: { from, to, label, arrows }
 */
export async function fetchGraph(maxNodes = 150) {
  const res = await fetch(`${BASE_URL}/api/graph/overview?max_nodes=${maxNodes}`);
  if (!res.ok) throw new Error(`Graph fetch failed: ${res.status}`);
  return res.json(); // { nodes, edges }
}

/**
 * GET /api/graph/expand/:nodeId
 * Returns { nodes, edges } — 1-hop neighbourhood
 *   nodes[i]: { id, label, title, color, type, key, ...attrs }
 *   edges[i]: { from, to, label, arrows }
 */
export async function expandNode(nodeId) {
  const res = await fetch(`${BASE_URL}/api/graph/expand/${encodeURIComponent(nodeId)}`);
  if (!res.ok) throw new Error(`Expand failed: ${res.status}`);
  return res.json(); // { nodes, edges }
}

/**
 * GET /api/graph/node/:nodeId
 * Returns full attribute payload for a single node.
 */
export async function fetchNode(nodeId) {
  const res = await fetch(`${BASE_URL}/api/graph/node/${encodeURIComponent(nodeId)}`);
  if (!res.ok) throw new Error(`Node fetch failed: ${res.status}`);
  return res.json();
}

/**
 * POST /api/chat
 * Body:  { message, history?, api_key? }
 * Returns:
 *   {
 *     response:         string,
 *     sql_used:         string | null,
 *     results_count:    number | null,
 *     query_results:    object[] | null,   // max 20 rows
 *     referenced_nodes: string[]
 *   }
 */
export async function askQuestion(message, history = [], apiKey = "") {
  const body = { message, history };
  if (apiKey) body.api_key = apiKey;

  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json();

  if (!res.ok) {
    // off_topic / llm_not_configured / llm_error shapes
    throw Object.assign(new Error(data.message || data.error || "Chat error"), {
      errorCode: data.error,
      payload: data,
    });
  }
  return data;
}

/**
 * GET /api/graph/stats
 */
export async function fetchStats() {
  const res = await fetch(`${BASE_URL}/api/graph/stats`);
  if (!res.ok) throw new Error(`Stats fetch failed: ${res.status}`);
  return res.json();
}

/**
 * POST /api/set-api-key
 */
export async function setApiKey(apiKey) {
  const res = await fetch(`${BASE_URL}/api/set-api-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error("Failed to set API key");
  return res.json();
}