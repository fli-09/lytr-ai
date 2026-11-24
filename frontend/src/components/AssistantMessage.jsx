import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function SourceChip({ source }) {
  const isCache = source === "LLM_CACHE";
  return (
    <span className={`chip chip--source ${isCache ? "chip--cache" : "chip--live"}`}>
      <span className="chip__icon" aria-hidden="true">{isCache ? "◆" : "●"}</span>
      <span className="chip__label">source</span>
      <span data-testid="meta-source" className="chip__value mono">{source}</span>
    </span>
  );
}

function Chip({ label, testId, value, title, wide }) {
  return (
    <span className={`chip${wide ? " chip--wide" : ""}`} title={title}>
      <span className="chip__label">{label}</span>
      <span data-testid={testId} className="chip__value mono">{value}</span>
    </span>
  );
}

export default function AssistantMessage({ reply, metadata }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(reply);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: ignore */
    }
  }

  const routing =
    metadata.resolution_source === "LLM_CACHE"
      ? "served from LiteLLM cache"
      : `answered by ${metadata.key_id}${metadata.fallback_attempts ? ` after ${metadata.fallback_attempts} failed key${metadata.fallback_attempts > 1 ? "s" : ""}` : ""}`;

  return (
    <article className="msg msg--assistant" data-testid="assistant-message" aria-label="Assistant reply">
      <div className="msg__avatar" aria-hidden="true">L</div>
      <div className="msg__body">
        <div className="msg__head">
          <span className="msg__author">Lyftr AI</span>
          <button type="button" className="icon-btn" onClick={copy} aria-label="Copy reply">
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{reply}</ReactMarkdown>
        </div>
        <div className="meta" aria-label="Request metadata">
          <SourceChip source={metadata.resolution_source} />
          <Chip label="model" testId="meta-model" value={metadata.model} title={metadata.model} wide />
          <Chip label="latency" testId="meta-latency" value={`${metadata.latency_ms} ms`} />
          <Chip label="in" testId="meta-input-tokens" value={metadata.input_tokens} title="Input tokens for this request" />
          <Chip label="out" testId="meta-output-tokens" value={metadata.output_tokens} title="Output tokens for this reply" />
          <span className={`meta__route${metadata.fallback_attempts ? " meta__route--fallback" : ""}`}>{routing}</span>
        </div>
      </div>
    </article>
  );
}
