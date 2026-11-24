import { useEffect, useMemo, useRef, useState } from "react";
import { sendChat } from "./lib/api.js";
import { createSessionId } from "./lib/session.js";
import HealthStatus from "./components/HealthStatus.jsx";
import AssistantMessage from "./components/AssistantMessage.jsx";
import Composer from "./components/Composer.jsx";
import SessionPanel from "./components/SessionPanel.jsx";
import { EmptyState, ErrorMessage, PendingMessage, UserMessage } from "./components/Messages.jsx";

let nextId = 0;
const uid = () => `m${++nextId}`;

export default function App() {
  const sessionId = useMemo(createSessionId, []); // new session per page load
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulateFailure, setSimulateFailure] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const inputRef = useRef(null);
  const endRef = useRef(null);
  const pendingRef = useRef(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items, pending]);

  async function send() {
    const message = draft.trim();
    if (!message || pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);

    const userItem = { id: uid(), type: "user", content: message };
    setItems((prev) => [...prev, userItem]);
    setDraft("");

    try {
      const data = await sendChat({ sessionId, message, systemPrompt, simulateFailure });
      setItems((prev) => [...prev, { id: uid(), type: "assistant", reply: data.reply, metadata: data.metadata }]);
    } catch (error) {
      setItems((prev) => [
        ...prev.map((item) => (item.id === userItem.id ? { ...item, failed: true } : item)),
        { id: uid(), type: "error", message: error.message, restore: message },
      ]);
    } finally {
      pendingRef.current = false;
      setPending(false);
      inputRef.current?.focus();
    }
  }

  function restore(text) {
    setDraft(text);
    inputRef.current?.focus();
  }

  return (
    <div className="shell">
      <aside className={`rail${panelOpen ? " rail--open" : ""}`} aria-label="Session settings">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">L</span>
          <span className="brand__name">Lyftr AI</span>
        </div>
        <SessionPanel
          sessionId={sessionId}
          systemPrompt={systemPrompt}
          onSystemPrompt={setSystemPrompt}
          simulateFailure={simulateFailure}
          onSimulateFailure={setSimulateFailure}
        />
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="topbar__brand">
            <span className="brand__mark" aria-hidden="true">L</span>
            <span className="brand__name">Lyftr AI</span>
          </div>
          <HealthStatus />
          <button
            type="button"
            className="topbar__toggle"
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen((open) => !open)}
          >
            {panelOpen ? "Close" : "Session"}
          </button>
        </header>

        {simulateFailure && (
          <div className="banner" role="note">
            Failover test active: next messages send <code>X-Simulate-Failure: {simulateFailure}</code>
          </div>
        )}

        <section className="conversation" aria-live="polite" aria-label="Conversation">
          <div className="conversation__inner">
            {items.length === 0 && !pending && <EmptyState onPick={restore} />}
            {items.map((item) => {
              if (item.type === "user") return <UserMessage key={item.id} content={item.content} failed={item.failed} />;
              if (item.type === "assistant")
                return <AssistantMessage key={item.id} reply={item.reply} metadata={item.metadata} />;
              return <ErrorMessage key={item.id} message={item.message} onRestore={() => restore(item.restore)} />;
            })}
            {pending && <PendingMessage />}
            <div ref={endRef} />
          </div>
        </section>

        <div className="composer-wrap">
          <Composer value={draft} onChange={setDraft} onSend={send} pending={pending} inputRef={inputRef} />
        </div>
      </main>
    </div>
  );
}
