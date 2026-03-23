"use client";

import { useEffect, useMemo, useState } from "react";

import ChatPanel from "@/components/ChatPanel";
import GraphCanvas from "@/components/GraphCanvas";
import NodeDetailsCard from "@/components/NodeDetailsCard";
import { askQuestion, expandNode, fetchGraph } from "@/lib/api";

const CATEGORY_CONFIG = [
  { id: "all", label: "All", color: "#8e9db0", types: [] },
  { id: "sales", label: "SalesOrder", color: "#4da3ff", types: ["sales_order"] },
  { id: "sales_item", label: "SalesOrderItem", color: "#7dc0ff", types: ["sales_order_item"] },
  { id: "delivery", label: "Delivery", color: "#70c1b3", types: ["delivery_document", "delivery_document_item"] },
  { id: "billing", label: "BillingDocument", color: "#71b8f6", types: ["billing_document", "billing_document_item"] },
  { id: "customer", label: "Customer", color: "#ff8db5", types: ["business_partner"] },
  { id: "product", label: "Product", color: "#f2b36f", types: ["product"] },
  { id: "finance", label: "JournalEntry", color: "#f5a1c0", types: ["journal_entry_item", "payment_ar_item"] }
];

function createMessage(role, text, sql = "") {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role,
    text,
    sql
  };
}

export default function HomePage() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [graphLoading, setGraphLoading] = useState(true);
  const [chatLoading, setChatLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [multiSelectEnabled, setMultiSelectEnabled] = useState(false);
  const [activeCategory, setActiveCategory] = useState("all");
  const [activeCategories, setActiveCategories] = useState(["all"]);
  const [messages, setMessages] = useState([
    createMessage("assistant", "Hi! I can help you analyze the Order to Cash process.")
  ]);

  useEffect(() => {
    let mounted = true;

    const loadGraph = async () => {
      try {
        const graph = await fetchGraph();
        if (!mounted) return;
        setGraphData({
          nodes: Array.isArray(graph.nodes) ? graph.nodes : [],
          edges: Array.isArray(graph.edges) ? graph.edges : []
        });
      } catch (error) {
        if (!mounted) return;
        setMessages((prev) => [
          ...prev,
          createMessage("assistant", `Graph load failed: ${error.message}`)
        ]);
      } finally {
        if (mounted) setGraphLoading(false);
      }
    };

    loadGraph();
    return () => {
      mounted = false;
    };
  }, []);

  const activeNodeForCard = useMemo(() => selectedNode || hoveredNode, [selectedNode, hoveredNode]);
  const filteredGraphData = useMemo(() => {
    if (multiSelectEnabled) {
      if (activeCategories.includes("all")) {
        return graphData;
      }
      const enabledTypes = new Set(
        CATEGORY_CONFIG
          .filter((item) => activeCategories.includes(item.id))
          .flatMap((item) => item.types)
      );
      const visibleNodes = (graphData?.nodes || []).filter((node) => enabledTypes.has(node.type));
      const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
      const visibleEdges = (graphData?.edges || []).filter(
        (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
      );
      return { nodes: visibleNodes, edges: visibleEdges };
    }

    if (activeCategory === "all") {
      return graphData;
    }

    const selected = CATEGORY_CONFIG.find((item) => item.id === activeCategory) || CATEGORY_CONFIG[0];
    const enabledTypes = new Set(selected.types);
    const visibleNodes = (graphData?.nodes || []).filter((node) => enabledTypes.has(node.type));
    const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
    const visibleEdges = (graphData?.edges || []).filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
    );
    return { nodes: visibleNodes, edges: visibleEdges };
  }, [graphData, activeCategory, multiSelectEnabled, activeCategories]);

  const handleMultiSelectChange = (event) => {
    const checked = event.target.checked;
    setMultiSelectEnabled(checked);

    if (checked) {
      setActiveCategories(activeCategory === "all" ? ["all"] : [activeCategory]);
      return;
    }

    const first = activeCategories.includes("all") ? "all" : activeCategories[0] || "all";
    setActiveCategory(first);
  };

  const handleCategoryClick = (categoryId) => {
    if (!multiSelectEnabled) {
      setActiveCategory(categoryId);
      return;
    }

    if (categoryId === "all") {
      setActiveCategories(["all"]);
      return;
    }

    setActiveCategories((prev) => {
      const withoutAll = prev.filter((id) => id !== "all");
      if (withoutAll.includes(categoryId)) {
        const next = withoutAll.filter((id) => id !== categoryId);
        return next.length > 0 ? next : ["all"];
      }
      return [...withoutAll, categoryId];
    });
  };

  const isCategoryActive = (categoryId) => {
    if (!multiSelectEnabled) {
      return activeCategory === categoryId;
    }
    return activeCategories.includes(categoryId);
  };

  const handleNodeClick = async (node) => {
    setSelectedNode(node);

    try {
      const expanded = await expandNode(node.id);
      const neighbors = Array.isArray(expanded.neighbors) ? expanded.neighbors : [];
      const edges = Array.isArray(expanded.edges) ? expanded.edges : [];

      if (neighbors.length === 0) return;

      setGraphData((prev) => {
        const nodeMap = new Map((prev.nodes || []).map((n) => [n.id, n]));
        const edgeSet = new Set((prev.edges || []).map((e) => `${e.source}__${e.target}__${e.relation}`));

        neighbors.forEach((n) => nodeMap.set(n.id, n));
        edges.forEach((e) => edgeSet.add(`${e.source}__${e.target}__${e.relation}`));

        return {
          nodes: Array.from(nodeMap.values()),
          edges: Array.from(edgeSet).map((edgeKey) => {
            const [source, target, relation] = edgeKey.split("__");
            return { source, target, relation };
          })
        };
      });
    } catch {
      // Non-blocking fallback: node selection still works if expand fails.
    }
  };

  const handleSend = async (question) => {
    setChatLoading(true);
    setMessages((prev) => [...prev, createMessage("user", question)]);

    try {
      const response = await askQuestion(question);
      const answerText = response?.answer || "No response generated.";
      const sql = response?.sql || "";
      setMessages((prev) => [...prev, createMessage("assistant", answerText, sql)]);
    } catch (error) {
      setMessages((prev) => [...prev, createMessage("assistant", `Request failed: ${error.message}`)]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <main className="page-root">
      <section className="left-pane">
        <header className="page-header">
          <span className="crumb-muted">Mapping</span>
          <span className="crumb-sep">/</span>
          <strong>Order to Cash</strong>
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
          {CATEGORY_CONFIG.map((category) => (
            <button
              key={category.id}
              type="button"
              className={`category-chip ${isCategoryActive(category.id) ? "active" : ""}`}
              onClick={() => handleCategoryClick(category.id)}
            >
              <span className="category-chip-dot" style={{ backgroundColor: category.color }} />
              {category.label}
            </button>
          ))}
        </div>

        <NodeDetailsCard node={activeNodeForCard} />
      </section>

      <ChatPanel messages={messages} onSend={handleSend} loading={chatLoading} />
    </main>
  );
}
