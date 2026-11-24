const FAILOVER_OPTIONS = [
  { value: "", label: "Off (normal request)" },
  { value: "key_1=429", label: "key_1 → 429 (rate limited)" },
  { value: "key_1=500", label: "key_1 → 500 (server error)" },
  { value: "*=429", label: "All keys → 429" },
];

export default function SessionPanel({ sessionId, systemPrompt, onSystemPrompt, simulateFailure, onSimulateFailure }) {
  return (
    <div className="panel">
      <section className="panel__section">
        <h2 className="panel__title">Session</h2>
        <p className="panel__mono mono" title={sessionId}>{sessionId}</p>
        <p className="panel__hint">A new session starts on every page load.</p>
      </section>

      <section className="panel__section">
        <label className="panel__title" htmlFor="system-prompt">Session instructions</label>
        <textarea
          id="system-prompt"
          data-testid="system-prompt-input"
          className="panel__textarea"
          placeholder="Optional system prompt, e.g. “Answer in one sentence.”"
          rows={4}
          value={systemPrompt}
          onChange={(event) => onSystemPrompt(event.target.value)}
        />
        <p className="panel__hint">Overrides the default system prompt for this session. Never shown in history.</p>
      </section>

      <section className="panel__section">
        <label className="panel__title" htmlFor="failover-test">Failover test</label>
        <select
          id="failover-test"
          className="panel__select"
          value={simulateFailure}
          onChange={(event) => onSimulateFailure(event.target.value)}
        >
          {FAILOVER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <p className="panel__hint">
          Sends <code>X-Simulate-Failure</code> with the next messages. Honoured only when the backend has
          ENABLE_FAILURE_SIMULATION=true; simulated requests skip the cache.
        </p>
      </section>
    </div>
  );
}
