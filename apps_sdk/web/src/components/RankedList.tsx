import { useRef, useState } from "react";
import type { RankedListingResult } from "../utils/api";

type RankedListProps = {
  results: RankedListingResult[];
  selectedId: string | null;
  onSelect: (listingId: string) => void;
  onInteract?: (listingId: string, eventType: "image_browse") => void;
};

function formatPrice(price?: number | null): string {
  if (price == null) return "Price n/a";
  return new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(price);
}

function getImageUrls(listing: RankedListingResult["listing"]): string[] {
  const candidates = [listing.hero_image_url, ...(listing.image_urls ?? [])].filter(
    (v): v is string => Boolean(v),
  );
  return Array.from(new Set(candidates));
}

export default function RankedList({ results, selectedId, onSelect, onInteract }: RankedListProps) {
  const [imageIndexes, setImageIndexes] = useState<Record<string, number>>({});
  const touchStartXRef = useRef<Record<string, number>>({});

  if (!results.length) {
    return (
      <div className="empty-state">
        <p>No results yet.</p>
        <p className="muted">Type a query below and press Search.</p>
      </div>
    );
  }

  return (
    <div className="ranked-list">
      {results.map((result, index) => {
        const listing = result.listing;
        const features = (listing.features ?? []).slice(0, 4);
        const imageUrls = getImageUrls(listing);
        const activeIndex = imageIndexes[result.listing_id] ?? 0;
        const activeImageUrl =
          imageUrls[(activeIndex + imageUrls.length) % Math.max(imageUrls.length, 1)];

        const advanceImage = (delta: number) => {
          onSelect(result.listing_id);
          if (imageUrls.length <= 1) return;
          onInteract?.(result.listing_id, "image_browse");
          setImageIndexes((current) => {
            const current_ = current[result.listing_id] ?? 0;
            const next = (current_ + delta + imageUrls.length) % imageUrls.length;
            return { ...current, [result.listing_id]: next };
          });
        };

        return (
          <div
            key={result.listing_id}
            className={`listing-card ${selectedId === result.listing_id ? "selected" : ""}`}
            onClick={() => onSelect(result.listing_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(result.listing_id);
              }
            }}
            role="button"
            tabIndex={0}
          >
            {activeImageUrl ? (
              <div className="listing-image-wrap">
                {imageUrls.length > 1 && (
                  <>
                    <button
                      aria-label="Previous image"
                      className="listing-image-button listing-image-button-prev"
                      onClick={(e) => { e.stopPropagation(); advanceImage(-1); }}
                      type="button"
                    >
                      ‹
                    </button>
                    <button
                      aria-label="Next image"
                      className="listing-image-button listing-image-button-next"
                      onClick={(e) => { e.stopPropagation(); advanceImage(1); }}
                      type="button"
                    >
                      ›
                    </button>
                    <div className="listing-image-count">
                      {activeIndex + 1}/{imageUrls.length}
                    </div>
                  </>
                )}
                <img
                  className="listing-image"
                  src={activeImageUrl}
                  alt={listing.title}
                  loading="lazy"
                  onTouchEnd={(e) => {
                    const startX = touchStartXRef.current[result.listing_id];
                    if (startX == null) return;
                    const endX = e.changedTouches[0]?.clientX;
                    if (typeof endX !== "number") return;
                    const deltaX = endX - startX;
                    if (Math.abs(deltaX) < 36) {
                      onSelect(result.listing_id);
                      return;
                    }
                    advanceImage(deltaX < 0 ? 1 : -1);
                  }}
                  onTouchStart={(e) => {
                    const touch = e.touches[0];
                    if (touch) touchStartXRef.current[result.listing_id] = touch.clientX;
                  }}
                />
              </div>
            ) : null}

            <div className="listing-card-header">
              <span className="listing-rank">#{index + 1}</span>
              <span className="listing-score">{result.score.toFixed(2)}</span>
            </div>
            <h2>{listing.title}</h2>
            <p className="listing-meta">
              {[listing.city, listing.canton].filter(Boolean).join(", ")}
            </p>
            <p className="listing-meta">
              {formatPrice(listing.price_chf)} · {listing.rooms ?? "?"} rooms
            </p>
            <p className="listing-reason">{result.reason}</p>
            {features.length > 0 && (
              <div className="feature-row">
                {features.map((f) => (
                  <span key={f} className="feature-badge">
                    {f.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
