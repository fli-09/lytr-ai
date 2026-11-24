export function UserMessage({ content, failed }) {
  return (
    <div className={`msg msg--user${failed ? " msg--failed" : ""}`}>
      <div className="msg__bubble">{content}</div>
      {failed && <span className="msg__note">Not delivered · not saved to history</span>}
    </div>
  );
}

export function ErrorMessage({ message, onRestore }) {
  return (
    <div className="msg msg--error" role="alert">
      <div className="msg__avatar msg__avatar--error" aria-hidden="true">!</div>
      <div className="msg__body">
        <p className="error__text">{message}</p>
        {onRestore && (
          <button type="button" className="text-btn" onClick={onRestore}>
            Put message back in the composer
          </button>
        )}
      </div>
    </div>
  );
}

export function PendingMessage() {
  return (
    <div className="msg msg--assistant msg--pending" aria-label="Waiting for reply">
      <div className="msg__avatar" aria-hidden="true">L</div>
      <div className="msg__body">
        <div className="typing" aria-hidden="true"><span /><span /><span /></div>
        <span className="sr-only">Lyftr AI is thinking…</span>
      </div>
    </div>
  );
}

const EXAMPLES = [
  "What is the capital of France?",
  "Explain LLM response caching in two sentences.",
  "Write a haiku about failover.",
];

export function EmptyState({ onPick }) {
  return (
    <div className="empty">
      <div className="empty__mark" aria-hidden="true">L</div>
      <h1 className="empty__title">Ask Lyftr AI anything</h1>
      <p className="empty__text">
        Multi-turn chat on a pooled set of API keys. Every reply shows where it came from: a live model call or
        LiteLLM&apos;s cache, plus its latency and tokens.
      </p>
      <div className="empty__examples">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="example" onClick={() => onPick(example)}>
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
