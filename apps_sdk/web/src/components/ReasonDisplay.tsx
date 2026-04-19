export type Segment = {
  type: "positive" | "moderate" | "negative" | "price" | "transit" | "info";
  text: string;
};

export const ICONS: Record<Segment["type"], string> = {
  positive: "↑",
  moderate: "→",
  negative: "↓",
  price: "CHF",
  transit: "⏱",
  info: "·",
};

export function parseReason(reason: string): Segment[] {
  return reason
    .split(" | ")
    .map((part) => part.trim())
    .filter((part) => Boolean(part) && !/^profile:/i.test(part))
    .map((part): Segment => {
      if (part.startsWith("+ ")) return { type: "positive", text: part.slice(2) };
      if (part.startsWith("- ")) return { type: "negative", text: part.slice(2) };
      if (/^~\d/.test(part)) return { type: "transit", text: part.slice(1).trim() };
      if (part.startsWith("~ ")) return { type: "moderate", text: part.slice(2) };
      if (part.includes("price")) return { type: "price", text: part };
      return { type: "info", text: part };
    });
}

export default function ReasonDisplay({ reason }: { reason: string }) {
  if (!reason) return null;
  const segments = parseReason(reason);
  if (!segments.length) return null;

  return (
    <div className="reason-badges">
      {segments.map((seg, i) => (
        <span key={i} className={`reason-badge reason-badge--${seg.type}`}>
          <span className="reason-icon">{ICONS[seg.type]}</span>
          {seg.text}
        </span>
      ))}
    </div>
  );
}
