const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:5000";

async function safeJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { error: "Invalid JSON response from server" };
  }
}

export async function fetchGraph() {
  const response = await fetch(`${API_BASE_URL}/graph`, {
    method: "GET",
    cache: "no-store"
  });
  const data = await safeJson(response);
  if (!response.ok) {
    throw new Error(data?.error || "Failed to fetch graph");
  }
  return data;
}

export async function askQuestion(question) {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question })
  });
  const data = await safeJson(response);
  if (!response.ok) {
    throw new Error(data?.error || "Failed to process query");
  }
  return data;
}

export async function expandNode(nodeId) {
  const response = await fetch(`${API_BASE_URL}/expand/${encodeURIComponent(nodeId)}`, {
    method: "GET",
    cache: "no-store"
  });
  const data = await safeJson(response);
  if (!response.ok) {
    throw new Error(data?.error || "Failed to expand node");
  }
  return data;
}
