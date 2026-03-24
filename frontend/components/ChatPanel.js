"use client";

import { useMemo, useRef, useEffect } from "react";
import { useState } from "react";

// ─── Markdown-lite renderer ──────────────────────────────────────────────────
// Handles **bold**, `inline code`, bullet lists, numbered lists, line breaks.
function RichText({ text }) {
  if (!text) return null;

  const lines = text.split("\n");

  return (
    <div className="rich-text">
      {lines.map((line, i) => {
        // Bullet list
        if (/^[-*•]\s+/.test(line)) {
          const content = line.replace(/^[-*•]\s+/, "");
          return <li key={i} className="rt-li">{renderInline(content)}</li>;
        }
        // Numbered list
        if (/^\d+\.\s+/.test(line)) {
          const content = line.replace(/^\d+\.\s+/, "");
          return <li key={i} className="rt-li rt-li-num">{renderInline(content)}</li>;
        }
        // Heading-ish lines (bold only line)
        if (/^\*\*.+\*\*$/.test(line.trim())) {
          return <p key={i} className="rt-heading">{renderInline(line)}</p>;
        }
        // Empty line → spacer
        if (line.trim() === "") return <div key={i} className="rt-spacer" />;
        return <p key={i} className="rt-p">{renderInline(line)}</p>;
      })}
    </div>
  );
}

function renderInline(text) {
  // Split on **bold** and `code` patterns
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (/^`[^`]+`$/.test(part)) {
      return <code key={i} className="rt-code">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

// ─── SQL block ───────────────────────────────────────────────────────────────
function SqlBlock({ sql, expanded, onToggle }) {
  return (
    <div className="sql-block">
      <button className="sql-toggle" onClick={onToggle}>
        <span className="sql-toggle-arrow">{expanded ? "▾" : "▸"}</span>
        SHOW GENERATED SQL
        {!expanded && <span className="sql-badge">SQL</span>}
      </button>
      {expanded && (
        <pre className="sql-pre">{sql}</pre>
      )}
    </div>
  );
}

// ─── Query results table ─────────────────────────────────────────────────────
function QueryResults({ rows, totalCount }) {
  if (!rows || rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  const hidden = totalCount > rows.length ? totalCount - rows.length : 0;

  return (
    <div className="qr-wrap">
      <div className="qr-header" style={{ background: "#e2e8f0" }}>
        <span>QUERY RESULTS</span>
        <span className="qr-count">{totalCount} ROWS</span>
      </div>
      <div className="qr-table-scroll">
        <table className="qr-table">
          <thead>
            <tr>
              {cols.map((c) => <th key={c}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <div className="qr-more">+ {hidden} more rows</div>
      )}
    </div>
  );
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function MessageBubble({ msg }) {
  const [sqlExpanded, setSqlExpanded] = useState(false);
  const isAssistant = msg.role === "assistant";

  return (
    <div className={`msg-row ${msg.role}`}>
      {isAssistant && (
        <div className="msg-avatar assistant"> D </div>
      )}

      <div className={`msg-bubble ${msg.role}`}>
        <p className="msg-role">{isAssistant ? "Dodge AI" : "You"}</p>

        {msg.isError ? (
          <p className="msg-error">{msg.text}</p>
        ) : isAssistant ? (
          <RichText text={msg.text} />
        ) : (
          <p>{msg.text}</p>
        )}

        {/* SQL block */}
        {msg.sql_used && (
          <SqlBlock
            sql={msg.sql_used}
            expanded={sqlExpanded}
            onToggle={() => setSqlExpanded((v) => !v)}
          />
        )}

        {/* Results table */}
        {msg.query_results && msg.query_results.length > 0 && (
          <QueryResults
            rows={msg.query_results}
            totalCount={msg.results_count ?? msg.query_results.length}
          />
        )}
      </div>

      {!isAssistant && (
        <div className="msg-avatar user">U</div>
      )}
    </div>
  );
}

// ─── Loading indicator ────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div className="msg-row assistant">
      <div className="msg-avatar assistant">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M8 12h8M12 8v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </div>
      <div className="msg-bubble assistant typing-bubble">
        <span /><span /><span />
      </div>
    </div>
  );
}

// ─── Main ChatPanel ───────────────────────────────────────────────────────────
export default function ChatPanel({ messages, onSend, loading }) {
  const [question, setQuestion] = useState("");
  const threadRef = useRef(null);

  const canSend = useMemo(
    () => question.trim().length > 0 && !loading,
    [question, loading]
  );

  // Auto-scroll to bottom
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const handleSubmit = (event) => {
    event.preventDefault();
    const value = question.trim();
    if (!value || loading) return;
    onSend(value);
    setQuestion("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <aside className="chat-panel">
      <div className="chat-panel-header">
        <p className="chat-header-small">Chat with Graph</p>
        <p className="chat-header-title">Order to Cash</p>
      </div>

      <div className="chat-thread" ref={threadRef}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {loading && <TypingDots />}
      </div>

      <form className="chat-input-wrap" onSubmit={handleSubmit}>
        <div className="chat-status">
          <span className="status-dot" />
          {loading ? "GraphIQ AI is thinking…" : "GraphIQ AI is awaiting instructions"}
        </div>
        <div className="chat-input-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Analyze anything…"
            disabled={loading}
          />
          <button type="submit" disabled={!canSend} style={{ color : "white", background : "black" }}>
            {loading ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="12" r="2"/><circle cx="6" cy="12" r="2"/><circle cx="18" cy="12" r="2"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2L15 22 11 13 2 9l20-7z"/>
              </svg>
            )}
          </button>
        </div>
      </form>
    </aside>
  );
}