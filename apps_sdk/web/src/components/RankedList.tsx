import { useEffect, useRef, useState } from "react";
import type { RankedListingResult } from "../utils/api";
import { resolveImageUrl } from "../utils/api";
import ReasonDisplay from "./ReasonDisplay";

type RankedListProps = {
  results: RankedListingResult[];
  selectedId: string | null;
  onSelect: (listingId: string) => void;
  onOpenDetail: (listingId: string) => void;
  onInteract?: (listingId: string, eventType: "image_browse") => void;
};

function formatPrice(price: number): string {
  return new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(price);
}

const SINGLE_UNIT_CATEGORIES = new Set([
  "einzelzimmer", "wg-zimmer", "einzelgarage",
  "parkplatz", "parkplatz, garage", "tiefgarage",
]);

function displayRooms(listing: RankedListingResult["listing"]): string {
  if (listing.rooms != null) return String(listing.rooms);
  if (listing.object_category && SINGLE_UNIT_CATEGORIES.has(listing.object_category.toLowerCase())) return "1";
  return "?";
}

function generateTitle(listing: RankedListingResult["listing"]): string {
  const rooms = listing.rooms ? `${listing.rooms}-room` : null;
  const category = listing.object_category
    ? listing.object_category.charAt(0).toUpperCase() +
      listing.object_category.slice(1).toLowerCase().replace(/_/g, " ")
    : "Property";
  const city = listing.city ?? null;
  return [rooms, category, city ? `· ${city}` : null].filter(Boolean).join(" ");
}

function getImageUrls(listing: RankedListingResult["listing"]): string[] {
  const candidates = [listing.hero_image_url, ...(listing.image_urls ?? [])]
    .filter((v): v is string => Boolean(v))
    .map(resolveImageUrl);
  return Array.from(new Set(candidates));
}

export default function RankedList({ results, selectedId, onSelect, onOpenDetail, onInteract }: RankedListProps) {
  const [imageIndexes, setImageIndexes] = useState<Record<string, number>>({});
  const touchStartXRef = useRef<Record<string, number>>({});
  const cardRefs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    if (selectedId && cardRefs.current[selectedId]) {
      cardRefs.current[selectedId]!.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedId]);

  const priced = results.filter((r) => r.listing.price_chf != null);

  if (!priced.length) {
    return (
      <div className="empty-state">
        <p>No results yet.</p>
        <p className="muted">Type a query below and press Search.</p>
      </div>
    );
  }

  return (
    <div className="ranked-list">
      {priced.map((result, index) => {
        const listing = result.listing;
        const features = (listing.features ?? []).slice(0, 5);
        const imageUrls = getImageUrls(listing);
        const activeIndex = imageIndexes[result.listing_id] ?? 0;
        const activeImageUrl =
          imageUrls[(activeIndex + imageUrls.length) % Math.max(imageUrls.length, 1)];

        const advanceImage = (delta: number) => {
          onSelect(result.listing_id);
          if (imageUrls.length <= 1) return;
          onInteract?.(result.listing_id, "image_browse");
          setImageIndexes((current) => {
            const cur = current[result.listing_id] ?? 0;
            return {
              ...current,
              [result.listing_id]: (cur + delta + imageUrls.length) % imageUrls.length,
            };
          });
        };

        return (
          <div
            key={result.listing_id}
            ref={(el) => { cardRefs.current[result.listing_id] = el; }}
            className={`listing-card ${selectedId === result.listing_id ? "selected" : ""}`}
            onClick={() => onOpenDetail(result.listing_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpenDetail(result.listing_id);
              }
            }}
            role="button"
            tabIndex={0}
          >
            {/* Image section — full width, fixed height */}
            {activeImageUrl ? (
              <div className="listing-image-wrap">
                {imageUrls.length > 1 && (
                  <>
                    <button
                      aria-label="Previous image"
                      className="listing-image-button listing-image-button-prev"
                      onClick={(e) => { e.stopPropagation(); advanceImage(-1); }}
                      type="button"
                    >‹</button>
                    <button
                      aria-label="Next image"
                      className="listing-image-button listing-image-button-next"
                      onClick={(e) => { e.stopPropagation(); advanceImage(1); }}
                      type="button"
                    >›</button>
                    <div className="listing-image-count">
                      {activeIndex + 1} / {imageUrls.length}
                    </div>
                  </>
                )}
                <img
                  className="listing-image"
                  src={activeImageUrl}
                  alt={listing.title}
                  loading="lazy"
                  onError={(e) => {
                    const wrap = (e.currentTarget as HTMLElement).closest(
                      ".listing-image-wrap",
                    ) as HTMLElement | null;
                    if (wrap) wrap.style.display = "none";
                  }}
                  onTouchEnd={(e) => {
                    const startX = touchStartXRef.current[result.listing_id];
                    if (startX == null) return;
                    const endX = e.changedTouches[0]?.clientX;
                    if (typeof endX !== "number") return;
                    const deltaX = endX - startX;
                    if (Math.abs(deltaX) < 36) { onSelect(result.listing_id); return; }
                    advanceImage(deltaX < 0 ? 1 : -1);
                  }}
                  onTouchStart={(e) => {
                    const touch = e.touches[0];
                    if (touch) touchStartXRef.current[result.listing_id] = touch.clientX;
                  }}
                />
              </div>
            ) : null}

            {/* Card body */}
            <div className="listing-card-body">
              {/* Price + rooms row */}
              <div className="listing-price-row">
                <span className="listing-price">{formatPrice(listing.price_chf!)}</span>
                <span className="listing-rooms">{displayRooms(listing)} rooms</span>
              </div>

              {/* Title */}
              <h2 className="listing-title">{generateTitle(listing)}</h2>

              {/* Location */}
              <p className="listing-meta">
                {[listing.city, listing.canton].filter(Boolean).join(", ")}
              </p>

              {/* Reason badges */}
              <ReasonDisplay reason={result.reason} />

              {/* Feature badges */}
              {features.length > 0 && (
                <div className="feature-row">
                  {features.map((f) => (
                    <span key={f} className="feature-badge">
                      {f.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
              )}

              {/* Footer: rank + ref */}
              <div className="listing-card-footer">
                <span className="listing-rank">#{index + 1}</span>
                <span className="listing-ref">ref {listing.id}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
