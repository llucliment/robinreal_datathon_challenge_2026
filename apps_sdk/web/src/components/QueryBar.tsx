import { useState } from "react";

type QueryBarProps = {
  onSearch: (query: string) => void;
  loading: boolean;
};

export default function QueryBar({ onSearch, loading }: QueryBarProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onSearch(trimmed);
  };

  return (
    <form className="query-bar" onSubmit={handleSubmit} role="search">
      <input
        className="query-input"
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="e.g. bright 3-room apartment in Zurich under 2800 CHF"
        disabled={loading}
        autoComplete="off"
      />
      <button
        className="query-submit"
        type="submit"
        disabled={loading || !value.trim()}
      >
        {loading ? <span className="query-spinner" aria-label="Searching…" /> : "Search"}
      </button>
    </form>
  );
}
