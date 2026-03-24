"use client";

// OLD graph_builder.py node shape:
//   { id: "sales_order:700001", type: "sales_order", metadata: { salesOrder, soldToParty, ... } }

const TYPE_ICONS = {
  sales_order:            "📦",
  sales_order_item:       "🔖",
  billing_document:       "🧾",
  billing_document_item:  "🧾",
  delivery_document:      "🚚",
  delivery_document_item: "🚚",
  business_partner:       "🏢",
  product:                "🛒",
  payment_ar_item:        "💳",
  journal_entry_item:     "📒",
};

const TYPE_COLORS = {
  sales_order:            "#4da3ff",
  sales_order_item:       "#7dc0ff",
  billing_document:       "#71b8f6",
  billing_document_item:  "#71b8f6",
  delivery_document:      "#70c1b3",
  delivery_document_item: "#70c1b3",
  business_partner:       "#ff8db5",
  product:                "#f2b36f",
  payment_ar_item:        "#f5a1c0",
  journal_entry_item:     "#f5a1c0",
};

function toTitle(value) {
  return String(value)
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (ch) => ch.toUpperCase());
}

function formatValue(key, value) {
  if (value === null || value === undefined || value === "") return "—";
  const v = String(value);
  if (key.toLowerCase().includes("amount") && !isNaN(Number(v))) {
    return Number(v).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return v;
}

export default function NodeDetailsCard({ node }) {
  if (!node) return null;

  const nodeType = node.type || "Node";
  const icon     = TYPE_ICONS[nodeType]  || "🔷";
  const accent   = TYPE_COLORS[nodeType] || "#4da3ff";

  // OLD shape: all display fields live in node.metadata
  // Fallback: if metadata missing, read directly from node (for safety)
  const fields = Object.entries(node.metadata || node).filter(
    ([k, v]) =>
      !["id", "type", "metadata", "color", "shape", "label", "group"].includes(k) &&
      v !== null &&
      v !== undefined &&
      v !== ""
  );

  return (
    <div className="node-card" style={{ "--accent": accent }}>
      <div className="node-card-header">
        <div>
          <h3 className="node-card-type" style={{ color: "black" }}>
            {toTitle(nodeType)}
          </h3>
          <p className="node-card-id">{node.id}</p>
        </div>
      </div>

      <div className="node-card-fields">
        {fields.length === 0 ? (
          <p className="node-card-empty">No additional attributes.</p>
        ) : (
          fields.map(([key, value]) => (
            <div key={key} className="node-card-row">
              <span className="node-card-key" style={{ color : "black" }}>{toTitle(key)}</span>
              <span className="node-card-val" style={{ color: "grey"}}>{formatValue(key, value)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}