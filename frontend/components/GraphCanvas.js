"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const TYPE_COLORS = {
  billing_document: "#71b8f6",
  billing_document_item: "#9fd0ff",
  sales_order: "#4da3ff",
  sales_order_item: "#7dc0ff",
  business_partner: "#ff8db5",
  payment_ar_item: "#ffb3cb",
  journal_entry_item: "#f5a1c0",
  delivery_document: "#70c1b3",
  delivery_document_item: "#a6ddd6",
  product: "#f2b36f"
};

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
    (graphData?.edges || []).forEach((edge) => {
      degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
      degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
    });

    const nodes = (graphData?.nodes || []).map((node) => ({
      ...node,
      color: TYPE_COLORS[node.type] || "#9db2c7",
      val: selectedNode?.id === node.id ? 12 : Math.max(6, Math.min(10, 6 + (degreeMap.get(node.id) || 0) * 0.35))
    }));

    const links = (graphData?.edges || []).map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      relation: edge.relation
    }));

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
    }, 260);
    return () => clearTimeout(timer);
  }, [loading, decoratedGraphData, canvasSize]);

  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <button type="button" className="ghost-btn" onClick={() => graphRef.current?.zoomToFit(700, 70)}>
          Fit to Screen
        </button>
        {/* <button type="button" className="solid-btn">
          Hide Granular Overlay
        </button> */}
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
            cooldownTicks={120}
            linkColor={() => "rgba(110, 169, 220, 0.30)"}
            linkWidth={(link) => (selectedNode && (link.source.id === selectedNode.id || link.target.id === selectedNode.id) ? 1.8 : 0.8)}
            nodeRelSize={6}
            nodeLabel={(node) => `${node.type}\n${node.id}`}
            onNodeClick={onNodeClick}
            onNodeHover={onNodeHover}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const label = node.metadata?.billingDocument || node.metadata?.salesOrder || node.metadata?.accountingDocument || node.id;
              const radius = node.val || 4;
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
              ctx.fillStyle = node.color;
              ctx.fill();

              if (selectedNode?.id === node.id) {
                ctx.lineWidth = 1.4;
                ctx.strokeStyle = "#133c63";
                ctx.stroke();
              }

              if (globalScale > 2.1) {
                const fontSize = 10 / globalScale;
                ctx.font = `${fontSize}px Inter, sans-serif`;
                ctx.fillStyle = "#2a4462";
                ctx.fillText(String(label), node.x + radius + 1.5, node.y + 1.5);
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
