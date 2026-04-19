import { useRef, useState } from "react";

const EXAMPLE_QUERIES = [
  "Quiet 2-room flat near ETH Zürich, max CHF 2'000 per month",
  "Spacious house with garden for sale in Zug or Lucerne",
  "Modern furnished studio, great public transport, under CHF 1'500",
];

type Props = {
  onSearch: (query: string) => void;
  loading: boolean;
};

export default function WelcomePage({ onSearch, loading }: Props) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || loading) return;
    onSearch(trimmed);
  };

  const handleExample = (q: string) => {
    setQuery(q);
    submit(q);
  };

  return (
    <div className="welcome-page">
      {/* Decorative geometric accents */}
      <div className="welcome-bg-accent welcome-bg-accent--tl" />
      <div className="welcome-bg-accent welcome-bg-accent--br" />

      <div className="welcome-content">
        {/* Brand */}
        <div className="welcome-brand">
          <span className="welcome-brand-mark" />
          RobinReal
        </div>

        {/* Hero text */}
        <div className="welcome-hero">
          <h1 className="welcome-title">
            Find your ideal<br />home in Switzerland
          </h1>
          <p className="welcome-subtitle">
            Describe exactly what you need — in plain language.
            Our AI reads your intent and ranks thousands of Swiss listings for you.
          </p>
        </div>

        {/* Search bar */}
        <form
          className="welcome-search"
          onSubmit={(e) => { e.preventDefault(); submit(query); }}
          role="search"
        >
          <input
            ref={inputRef}
            className="welcome-search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. bright 3-room apartment in Zürich under CHF 2'800…"
            disabled={loading}
            autoFocus
            autoComplete="off"
          />
          <button
            className="welcome-search-btn"
            type="submit"
            disabled={loading || !query.trim()}
          >
            {loading
              ? <span className="query-spinner" aria-label="Searching…" />
              : "Search"}
          </button>
        </form>

        {/* Quick-start chips */}
        <div className="welcome-examples">
          <span className="welcome-examples-label">Try →</span>
          <div className="welcome-chips">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                className="welcome-chip"
                onClick={() => handleExample(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer attribution */}
      <p className="welcome-footer">
        Zurich Datathon 2026 · RobinReal Team
      </p>
    </div>
  );
}
