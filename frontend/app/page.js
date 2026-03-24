// app/page.js
"use client";

import { useEffect, useMemo, useState } from "react";

import ChatPanel from "@/components/ChatPanel";
import GraphCanvas from "@/components/GraphCanvas";
import NodeDetailsCard from "@/components/NodeDetailsCard";
import { askQuestion, expandNode, fetchGraph } from "@/lib/api";
import { FaGithub } from "react-icons/fa";


const normalizeType = (type = "") =>
  type
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .toLowerCase();


// ─── Category config — type strings match OLD graph_builder.py exactly ────────
const CATEGORY_CONFIG = [
  { id: "all", label: "All", color: "#313131", types: [] },
  {
    id: "sales",
    label: "Sales",
    color: "#4A90D9",
    types: ["sales_order", "sales_order_item"]
  },
  {
    id: "billing",
    label: "Billing",
    color: "#ea7eff",
    types: ["billing_document"]
  },
  {
    id: "customer",
    label: "Customer",
    color: "#8E44AD",
    types: ["business_partner"]
  },
  {
    id: "product",
    label: "Product",
    color: "#F39C12",
    types: ["product", "plant"]
  },
  {
    id: "finance",
    label: "Finance",
    color: "#78909C",
    types: ["journal_entry", "payment"]
  },
  {
    id: "delivery",
    label: "Delivery",
    color: "#E74C3C",
    types: ["outbound_delivery"]
  },
];

// ─── Message helpers ──────────────────────────────────────────────────────────
function createMessage(role, payload) {
  const isString = typeof payload === "string";
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role,
    text:             isString ? payload : (payload.response || ""),
    sql_used:         isString ? null    : (payload.sql_used || null),
    results_count:    isString ? null    : (payload.results_count ?? null),
    query_results:    isString ? null    : (payload.query_results || null),
    referenced_nodes: isString ? []      : (payload.referenced_nodes || []),
    isError: false,
  };
}

function createErrorMessage(text) {
  return {
    id: `assistant-err-${Date.now()}`,
    role: "assistant",
    text,
    sql_used: null, results_count: null,
    query_results: null, referenced_nodes: [],
    isError: true,
  };
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function HomePage() {
  const [graphData, setGraphData]       = useState({ nodes: [], edges: [] });
  const [graphLoading, setGraphLoading] = useState(true);
  const [chatLoading, setChatLoading]   = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode]   = useState(null);
  const [multiSelectEnabled, setMultiSelectEnabled] = useState(false);
  const [activeCategory, setActiveCategory]         = useState("all");
  const [activeCategories, setActiveCategories]     = useState(["all"]);
  const [chatHistory, setChatHistory]   = useState([]);
  const [messages, setMessages] = useState([
    createMessage("assistant", "Hi! I can help you analyze the **Order to Cash** process. Ask me anything about sales orders, billing documents, deliveries, or payments."),
  ]);

  // ── Load graph ────────────────────────────────────────────────────────────
  // OLD graph_builder.get_graph() returns:
  //   { nodes: [{id, type, metadata:{...}}], edges: [{source, target, relation}] }
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = await fetchGraph();
        if (!mounted) return;
        setGraphData({
          nodes: Array.isArray(data.nodes) ? data.nodes : [],
          edges: Array.isArray(data.edges) ? data.edges : [],
        });
      } catch (err) {
        if (!mounted) return;
        setMessages((prev) => [
          ...prev,
          createErrorMessage(`Graph load failed: ${err.message}`),
        ]);
      } finally {
        if (mounted) setGraphLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  // ── Derived: node for details card ────────────────────────────────────────
  const activeNodeForCard = useMemo(
    () => selectedNode || hoveredNode,
    [selectedNode, hoveredNode]
  );

  // ── Derived: filtered graph ───────────────────────────────────────────────
  const filteredGraphData = useMemo(() => {
    const isAll = multiSelectEnabled
      ? activeCategories.includes("all")
      : activeCategory === "all";

    if (isAll) return graphData;

    const activeTypes = new Set(
      CATEGORY_CONFIG.filter((c) =>
        multiSelectEnabled
          ? activeCategories.includes(c.id)
          : c.id === activeCategory
      ).flatMap((c) => c.types)
    );

    if (activeTypes.size === 0) return graphData;

    const visibleNodes = (graphData.nodes || []).filter((n) =>
      activeTypes.has(normalizeType(n.type))
    );
    const visibleIds   = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = (graphData.edges || []).filter(
      (e) => {
        const src = e.source || e.from;
        const tgt = e.target || e.to;
        return visibleIds.has(src) && visibleIds.has(tgt);
      }
    );
    return { nodes: visibleNodes, edges: visibleEdges };
  }, [graphData, activeCategory, activeCategories, multiSelectEnabled]);

  // ── Category controls ─────────────────────────────────────────────────────
  const handleMultiSelectChange = (e) => {
    const checked = e.target.checked;
    setMultiSelectEnabled(checked);
    if (checked) {
      setActiveCategories(activeCategory === "all" ? ["all"] : [activeCategory]);
    } else {
      setActiveCategory(
        activeCategories.includes("all") ? "all" : activeCategories[0] || "all"
      );
    }
  };

  const handleCategoryClick = (id) => {
    if (!multiSelectEnabled) { setActiveCategory(id); return; }
    if (id === "all") { setActiveCategories(["all"]); return; }
    setActiveCategories((prev) => {
      const without = prev.filter((x) => x !== "all");
      if (without.includes(id)) {
        const next = without.filter((x) => x !== id);
        return next.length > 0 ? next : ["all"];
      }
      return [...without, id];
    });
  };

  const isCategoryActive = (id) =>
    multiSelectEnabled ? activeCategories.includes(id) : activeCategory === id;

  // ── Node click → expand ───────────────────────────────────────────────────
  // OLD get_neighbors returns: { node, neighbors: [...], edges: [...] }
  const handleNodeClick = async (node) => {
    setSelectedNode(node);
    try {
      const expanded = await expandNode(node.id);

      // neighbors = array of node objects, edges = [{source, target, relation}]
      const neighbors = Array.isArray(expanded.neighbors) ? expanded.neighbors : [];
      const edges     = Array.isArray(expanded.edges)     ? expanded.edges     : [];

      if (neighbors.length === 0) return;

      setGraphData((prev) => {
        const nodeMap = new Map((prev.nodes || []).map((n) => [n.id, n]));
        neighbors.forEach((n) => nodeMap.set(n.id, n));

        const edgeKey = (e) => `${e.source}__${e.target}__${e.relation}`;
        const edgeMap = new Map((prev.edges || []).map((e) => [edgeKey(e), e]));
        edges.forEach((e) => edgeMap.set(edgeKey(e), e));

        return {
          nodes: Array.from(nodeMap.values()),
          edges: Array.from(edgeMap.values()),
        };
      });
    } catch {
      // Non-blocking — selection still works without expansion
    }
  };

  // ── Chat ──────────────────────────────────────────────────────────────────
  const handleSend = async (question) => {
    setChatLoading(true);
    setMessages((prev) => [...prev, createMessage("user", question)]);

    const historyToSend = chatHistory.slice(-4).map((m) => ({
      role: m.role, content: m.text,
    }));

    try {
      const data = await askQuestion(question, historyToSend);
      setMessages((prev) => [...prev, createMessage("assistant", data)]);
      setChatHistory((prev) => [
        ...prev,
        { role: "user",      text: question },
        { role: "assistant", text: data.response || "" },
      ]);
    } catch (err) {
      const text = err.message?.includes("off_topic")
        ? "This system is designed to answer questions related to the SAP Order-to-Cash dataset only."
        : err.message?.includes("llm_not_configured")
        ? "No LLM API key configured. Please set a Gemini API key in the backend."
        : `Request failed: ${err.message}`;
      setMessages((prev) => [...prev, createErrorMessage(text)]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <main className="page-root">
      <section className="left-pane">
        <header className="page-header">
          <div className="header-left">
            <span className="crumb-muted">Mapping</span>
            <span className="crumb-sep">/</span>
            <strong>Order to Cash</strong>
          </div>

          <div className="header-right">
            <p style={{ color: "grey", fontSize: "12px" }}>
              sidduramagiri3@gmail.com
            </p>
            <a
              href="https://github.com/siddharthramagiri/Dodge-AI-fde"
              target="_blank"
              rel="noopener noreferrer"
              className="github-link"
            >
              <FaGithub size={18} />
            </a>
          </div>
        </header>

        <GraphCanvas
          graphData={filteredGraphData}
          selectedNode={selectedNode}
          onNodeClick={handleNodeClick}
          onNodeHover={setHoveredNode}
          loading={graphLoading}
        />

        <div className="category-toggle-bar">
          <label className="multi-select-toggle">
            <input
              type="checkbox"
              checked={multiSelectEnabled}
              onChange={handleMultiSelectChange}
            />
            Multi-select
          </label>
          {CATEGORY_CONFIG.map((cat) => (
            <button
              key={cat.id}
              type="button"
              className={`category-chip ${isCategoryActive(cat.id) ? "active" : ""}`}
              onClick={() => handleCategoryClick(cat.id)}
            >
              <span className="category-chip-dot" style={{ backgroundColor: cat.color }} />
              {cat.label}
            </button>
          ))}
        </div>

        <NodeDetailsCard node={activeNodeForCard} />
      </section>

      <ChatPanel
        messages={messages}
        onSend={handleSend}
        loading={chatLoading}
      />
    </main>
  );
}