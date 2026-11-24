import { useEffect, useRef } from "react";

const MAX_CHARS = 4000;

export default function Composer({ value, onChange, onSend, pending, inputRef }) {
  const localRef = useRef(null);
  const ref = inputRef || localRef;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value, ref]);

  const trimmedLength = value.trim().length;
  const tooLong = trimmedLength > MAX_CHARS;
  const canSend = !pending && trimmedLength > 0;

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSend();
    }
  }

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      <label htmlFor="chat-input" className="sr-only">Message</label>
      <textarea
        id="chat-input"
        ref={ref}
        data-testid="chat-input"
        className="composer__input"
        placeholder="Message Lyftr AI…  (Enter to send, Shift+Enter for a new line)"
        rows={1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        aria-describedby="composer-hint"
      />
      <div className="composer__bar">
        <span id="composer-hint" className={`composer__count mono${tooLong ? " composer__count--over" : ""}`}>
          {trimmedLength}/{MAX_CHARS}
        </span>
        <button type="submit" data-testid="send-button" className="send-btn" disabled={!canSend} aria-busy={pending}>
          {pending ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">↑</span>}
          <span className="send-btn__label">{pending ? "Sending" : "Send"}</span>
        </button>
      </div>
    </form>
  );
}
