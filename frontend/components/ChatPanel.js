"use client";

import { useMemo, useState } from "react";

export default function ChatPanel({ messages, onSend, loading }) {
  const [question, setQuestion] = useState("");

  const canSend = useMemo(() => question.trim().length > 0 && !loading, [question, loading]);

  const handleSubmit = (event) => {
    event.preventDefault();
    const value = question.trim();
    if (!value) return;
    onSend(value);
    setQuestion("");
  };

  return (
    <aside className="chat-panel">
      <div className="chat-panel-header">
        <p className="chat-header-small">Chat with Graph</p>
        <p className="chat-header-title">Order to Cash</p>
      </div>

      <div className="chat-thread">
        {messages.map((msg) => (
          <div key={msg.id} className={`msg-row ${msg.role}`}>
            {msg.role === "assistant" ? <div className="msg-avatar assistant">D</div> : null}
            <div className={`msg-bubble ${msg.role}`}>
              <p className="msg-role">{msg.role === "user" ? "You" : "Dodge AI"}</p>
              <p>{msg.text}</p>
              {msg.sql ? <pre className="msg-sql">{msg.sql}</pre> : null}
            </div>
            {msg.role === "user" ? <div className="msg-avatar user" >U</div> : null}
          </div>
        ))}
      </div>

      <form className="chat-input-wrap" onSubmit={handleSubmit}>
        <div className="chat-status">
          <span className="status-dot" />
          Dodge AI is awaiting instructions
        </div>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Analyze anything"
          disabled={loading}
        />
        <button type="submit" disabled={!canSend}>
          {loading ? "..." : "Send"}
        </button>
      </form>
    </aside>
  );
}
