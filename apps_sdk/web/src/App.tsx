import { useEffect, useMemo, useRef, useState } from "react";
import ListingsMap from "./components/ListingsMap";
import QueryBar from "./components/QueryBar";
import RankedList from "./components/RankedList";
import type { RankedListingResult } from "./utils/api";
import { logInteraction, searchListings } from "./utils/api";
import { getUserId } from "./utils/userId";

// ---------------------------------------------------------------------------
// MCP / ChatGPT tool-output types (kept for backwards compatibility)
// ---------------------------------------------------------------------------
type ToolOutput = {
  listings?: RankedListingResult[];
  meta?: Record<string, unknown>;
};

declare global {
  interface Window {
    openai?: { toolOutput?: ToolOutput };
  }
}

type UiToolResultMessage = {
  jsonrpc?: string;
  method?: string;
  params?: { structuredContent?: ToolOutput };
};

function readToolOutput(): ToolOutput {
  return window.openai?.toolOutput ?? {};
}

function readToolOutputFromMessage(message: unknown): ToolOutput | null {
  if (!message || typeof message !== "object") return null;
  const m = message as UiToolResultMessage;
  if (m.jsonrpc !== "2.0" || m.method !== "ui/notifications/tool-result") return null;
  return m.params?.structuredContent ?? {};
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DWELL_THRESHOLD_MS = 3_000;

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
export default function App() {
  const userId = useMemo(() => getUserId(), []);

  // Direct search state
  const [searchResults, setSearchResults] = useState<RankedListingResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState("");

  // MCP tool output (backwards compat — used when no direct search has been done)
  const [toolOutput, setToolOutput] = useState<ToolOutput>(() => readToolOutput());

  // Selected listing for map highlight
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Dwell-time tracking
  const dwellRef = useRef<{ id: string; startedAt: number } | null>(null);

  // MCP event listeners
  useEffect(() => {
    const onGlobals = (event: Event) => {
      const e = event as CustomEvent<{ globals?: { toolOutput?: ToolOutput } }>;
      setToolOutput(e.detail?.globals?.toolOutput ?? readToolOutput());
    };
    window.addEventListener("openai:set_globals", onGlobals as EventListener);

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return;
      const next = readToolOutputFromMessage(event.data);
      if (next) setToolOutput(next);
    };
    window.addEventListener("message", onMessage, { passive: true });

    return () => {
      window.removeEventListener("openai:set_globals", onGlobals as EventListener);
      window.removeEventListener("message", onMessage);
    };
  }, []);

  // Direct search results take priority; fall back to MCP tool output
  const results: RankedListingResult[] =
    searchResults.length > 0 ? searchResults : (toolOutput.listings ?? []);

  // Keep selectedId in sync when results change
  useEffect(() => {
    if (!results.length) {
      setSelectedId(null);
      return;
    }
    setSelectedId((current) =>
      current && results.some((r) => r.listing_id === current)
        ? current
        : results[0].listing_id,
    );
  }, [results]);

  const selectedListing = useMemo(
    () => results.find((r) => r.listing_id === selectedId) ?? null,
    [results, selectedId],
  );

  // -------------------------------------------------------------------------
  // Interaction handlers
  // -------------------------------------------------------------------------
  const handleSelect = (listingId: string) => {
    const now = Date.now();

    // Fire "view" for the previous selection if the user spent enough time
    if (dwellRef.current && dwellRef.current.id !== listingId) {
      const elapsed = now - dwellRef.current.startedAt;
      if (elapsed >= DWELL_THRESHOLD_MS) {
        logInteraction(userId, dwellRef.current.id, "view", lastQuery);
      }
    }

    dwellRef.current = { id: listingId, startedAt: now };
    setSelectedId(listingId);
    logInteraction(userId, listingId, "click", lastQuery);
  };

  const handleInteract = (listingId: string, eventType: "image_browse") => {
    logInteraction(userId, listingId, eventType, lastQuery);
  };

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setLastQuery(query);
    try {
      const data = await searchListings(query, userId);
      setSearchResults(data.listings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-header">
          <p className="eyebrow">RobinReal</p>
          <h1>Listings</h1>
          <p className="muted">
            {results.length
              ? `${results.length} result${results.length === 1 ? "" : "s"}`
              : "Enter a query to find properties"}
          </p>
          {error && <p className="search-error">{error}</p>}
        </div>
        <RankedList
          results={results}
          selectedId={selectedId}
          onSelect={handleSelect}
          onInteract={handleInteract}
        />
      </aside>

      <main className="map-panel">
        <ListingsMap
          results={results}
          selectedId={selectedId}
          selectedListing={selectedListing}
          onSelect={handleSelect}
        />
        <QueryBar onSearch={handleSearch} loading={loading} />
      </main>
    </div>
  );
}
