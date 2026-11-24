import { useEffect, useState } from "react";
import { getHealth } from "../lib/api.js";

const LABELS = {
  checking: "Checking backend",
  ok: "Backend ready",
  down: "Backend unavailable",
};

// Driven only by real GET /health responses. /health confirms the app, the
// database and the loaded key pool; it does not claim every provider key works.
export default function HealthStatus() {
  const [state, setState] = useState({ status: "checking", info: null });

  useEffect(() => {
    let cancelled = false;
    let controller;
    async function check() {
      controller = new AbortController();
      try {
        const info = await getHealth(controller.signal);
        if (!cancelled) setState({ status: info?.status === "ok" ? "ok" : "down", info });
      } catch {
        if (!cancelled) setState({ status: "down", info: null });
      }
    }
    check();
    const timer = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
      controller?.abort();
    };
  }, []);

  const { status, info } = state;
  const title =
    status === "ok"
      ? `${info.keys_configured} keys loaded · cache ${info.cache_enabled ? "enabled" : "disabled"}`
      : LABELS[status];

  return (
    <div className={`health health--${status}`} role="status" aria-live="polite" title={title}>
      <span className="health__dot" aria-hidden="true" />
      <span className="health__label">{LABELS[status]}</span>
      {status === "ok" && (
        <span className="health__detail">
          {info.keys_configured} keys · cache {info.cache_enabled ? "on" : "off"}
        </span>
      )}
    </div>
  );
}
