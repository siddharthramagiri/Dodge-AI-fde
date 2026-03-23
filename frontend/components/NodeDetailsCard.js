"use client";

export default function NodeDetailsCard({ node }) {
  if (!node) return null;

  const metadata = node.metadata || {};
  const metadataEntries = Object.entries(metadata);

  return (
    <div className="node-card">
      <h3>{toTitle(node.type || "Node")}</h3>
      <p className="node-card-subtle">
        Entity: <strong>{node.type || "unknown"}</strong>
      </p>
      <p className="node-card-subtle">
        ID: <strong>{node.id}</strong>
      </p>
      <div className="node-card-fields">
        {metadataEntries.length === 0 ? (
          <p className="node-card-empty">No metadata available.</p>
        ) : (
          metadataEntries.map(([key, value]) => (
            <div key={key} className="node-card-row">
              <span>{toTitle(key)}:</span>
              <span>{String(value)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function toTitle(value) {
  return value
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (ch) => ch.toUpperCase());
}
