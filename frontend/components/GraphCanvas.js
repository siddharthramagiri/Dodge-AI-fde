"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const TYPE_COLORS = {
  billing_document: "#ea7eff",
  billing_document_item: "#9fd0ff",
  sales_order: "#4A90D9",
  sales_order_item: "#865bff",
  business_partner: "#8E44AD",
  payment_ar_item: "#ffb3cb",
  journal_entry_item: "#E74C3C",
  delivery_document: "#E74C3C",
  delivery_document_item: "#a6ddd6",
  product: "#F39C12"
};

// 🔥 normalize backend types (SalesOrder → sales_order)
const normalizeType = (type = "") =>
  type
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .toLowerCase();

export default function GraphCanvas({
  graphData,
  selectedNode,
  onNodeClick,
  onNodeHover,
  loading
}) {
  const graphRef = useRef(null);
  const canvasContainerRef = useRef(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });

  const decoratedGraphData = useMemo(() => {
    const degreeMap = new Map();

    // ✅ HANDLE BOTH FORMATS (source/target OR from/to)
    (graphData?.edges || []).forEach((edge) => {
      const src = edge.source || edge.from;
      const tgt = edge.target || edge.to;

      if (!src || !tgt) return;

      degreeMap.set(src, (degreeMap.get(src) || 0) + 1);
      degreeMap.set(tgt, (degreeMap.get(tgt) || 0) + 1);
    });

    const nodes = (graphData?.nodes || []).map((node) => {
      const type = normalizeType(node.type);

      return {
        ...node,
        type,
        color: TYPE_COLORS[type] || "#9db2c7",
        val:
          selectedNode?.id === node.id
            ? 12
            : Math.max(6, Math.min(10, 6 + (degreeMap.get(node.id) || 0) * 0.4))
      };
    });

    const links = (graphData?.edges || []).map((edge, index) => {
      const source = edge.source || edge.from;
      const target = edge.target || edge.to;

      return {
        id: `${source}-${target}-${index}`,
        source,
        target,
        relation: edge.relation || edge.label || ""
      };
    });

    return { nodes, links };
  }, [graphData, selectedNode]);

  useEffect(() => {
    const el = canvasContainerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      setCanvasSize({
        width: Math.max(1, Math.floor(rect.width)),
        height: Math.max(1, Math.floor(rect.height))
      });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (loading) return;

    const timer = setTimeout(() => {
      graphRef.current?.zoomToFit(700, 70);
    }, 300);

    return () => clearTimeout(timer);
  }, [loading, decoratedGraphData, canvasSize]);

  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <button
          type="button"
          className="ghost-btn"
          onClick={() => graphRef.current?.zoomToFit(700, 70)}
        >
          Fit to Screen
        </button>
      </div>

      <div className="graph-canvas" ref={canvasContainerRef}>
        {loading ? (
          <div className="graph-empty-state">Loading graph...</div>
        ) : canvasSize.width > 0 && canvasSize.height > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            width={canvasSize.width}
            height={canvasSize.height}
            graphData={decoratedGraphData}

            // 🔥 better physics = connected graph
            cooldownTicks={150}
            d3VelocityDecay={0.3}

            linkColor={() => "rgba(110, 169, 220, 0.35)"}
            linkWidth={(link) =>
              selectedNode &&
              (link.source.id === selectedNode.id ||
                link.target.id === selectedNode.id)
                ? 1.8
                : 0.8
            }

            nodeRelSize={6}
            nodeLabel={(node) => `${node.type}\n${node.id}`}

            onNodeClick={onNodeClick}
            onNodeHover={onNodeHover}

            nodeCanvasObject={(node, ctx, globalScale) => {
              const label =
                node.metadata?.billingDocument ||
                node.metadata?.salesOrder ||
                node.metadata?.accountingDocument ||
                node.id;

              const radius = node.val || 4;

              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
              ctx.fillStyle = node.color;
              ctx.fill();

              if (selectedNode?.id === node.id) {
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = "#133c63";
                ctx.stroke();
              }

              if (globalScale > 2.2) {
                const fontSize = 10 / globalScale;
                ctx.font = `${fontSize}px Inter, sans-serif`;
                ctx.fillStyle = "#2a4462";
                ctx.fillText(
                  String(label),
                  node.x + radius + 2,
                  node.y + 2
                );
              }
            }}
          />
        ) : (
          <div className="graph-empty-state">Preparing graph...</div>
        )}
      </div>
    </div>
  );
}