import { useEffect, useState } from "react";
import type { RankedListingResult } from "../utils/api";
import { resolveImageUrl } from "../utils/api";
import { parseReason, ICONS } from "./ReasonDisplay";

type Props = {
  result: RankedListingResult;
  onClose: () => void;
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
  return [rooms, category, city ? `in ${city}` : null].filter(Boolean).join(" ");
}

function getImageUrls(listing: RankedListingResult["listing"]): string[] {
  const candidates = [listing.hero_image_url, ...(listing.image_urls ?? [])]
    .filter((v): v is string => Boolean(v))
    .map(resolveImageUrl);
  return Array.from(new Set(candidates));
}

// Converts **bold** markdown and bare \n to HTML for dangerouslySetInnerHTML
function renderDescription(raw: string): string {
  return raw
    .replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

export default function ListingDetail({ result, onClose }: Props) {
  const { listing } = result;
  const allImageUrls = getImageUrls(listing);

  const [activeIndex, setActiveIndex] = useState(0);
  const [failedUrls, setFailedUrls] = useState<Set<string>>(new Set());

  // Only render images that haven't errored
  const visibleImages = allImageUrls.filter((u) => !failedUrls.has(u));
  const count = visibleImages.length;
  const clampedIndex = count > 0 ? ((activeIndex % count) + count) % count : 0;

  const prev = () => setActiveIndex((i) => i - 1);
  const next = () => setActiveIndex((i) => i + 1);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Lock body scroll while open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const segments = parseReason(result.reason);
  const pros     = segments.filter((s) => s.type === "positive");
  const cons     = segments.filter((s) => s.type === "negative" || s.type === "moderate");
  const infoItems = segments.filter((s) => s.type === "transit" || s.type === "price" || s.type === "info");

  const hasCoords = typeof listing.latitude === "number" && typeof listing.longitude === "number";
  const mapsUrl = hasCoords
    ? `https://www.google.com/maps/search/?api=1&query=${listing.latitude},${listing.longitude}`
    : null;

  const features = listing.features ?? [];

  return (
    <div className="detail-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>

        {/* Back button */}
        <button className="detail-back" onClick={onClose} type="button">
          ← Back to results
        </button>

        {/* ── Sliding photo gallery ── */}
        {visibleImages.length > 0 ? (
          <div className="detail-gallery">
            {/* Sliding track — all images side by side */}
            <div
              className="detail-gallery-track"
              style={{ transform: `translateX(-${clampedIndex * 100}%)` }}
            >
              {visibleImages.map((url) => (
                <div key={url} className="detail-gallery-slide">
                  <img
                    src={url}
                    alt={listing.title}
                    className="detail-gallery-img"
                    onError={() => setFailedUrls((prev) => new Set([...prev, url]))}
                  />
                </div>
              ))}
            </div>

            {count > 1 && (
              <>
                <button type="button" aria-label="Previous image"
                  className="detail-gallery-btn detail-gallery-prev" onClick={prev}>‹</button>
                <button type="button" aria-label="Next image"
                  className="detail-gallery-btn detail-gallery-next" onClick={next}>›</button>
                <span className="detail-gallery-count">
                  {clampedIndex + 1} / {count}
                </span>
              </>
            )}
          </div>
        ) : (
          <div className="detail-gallery detail-gallery--empty" />
        )}

        {/* ── Content ── */}
        <div className="detail-content">

          {/* Header: title + price */}
          <div className="detail-header">
            <div className="detail-header-left">
              <h1 className="detail-title">{generateTitle(listing)}</h1>
              <p className="detail-location">
                {[listing.city, listing.canton].filter(Boolean).join(", ")}
                {listing.offer_type && (
                  <span className="detail-offer-badge">
                    {listing.offer_type === "RENT" ? "For rent" : "For sale"}
                  </span>
                )}
              </p>
            </div>
            <div className="detail-price-block">
              {listing.price_chf != null && (
                <span className="detail-price">{formatPrice(listing.price_chf)}</span>
              )}
              <span className="detail-rooms">{displayRooms(listing)} rooms</span>
              {listing.living_area_sqm != null && (
                <span className="detail-area">{listing.living_area_sqm} m²</span>
              )}
            </div>
          </div>

          {/* Google Maps CTA */}
          {mapsUrl && (
            <a href={mapsUrl} target="_blank" rel="noopener noreferrer" className="detail-maps-btn">
              <span>📍</span> Open in Google Maps
            </a>
          )}

          {/* Why this matches */}
          {segments.length > 0 && (
            <section className="detail-section">
              <h2 className="detail-section-title">Why this matches your search</h2>
              <div className="reason-badges">
                {segments.map((seg, i) => (
                  <span key={i} className={`reason-badge reason-badge--${seg.type}`}>
                    <span className="reason-icon">{ICONS[seg.type]}</span>
                    {seg.text}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Pros & Cons */}
          {(pros.length > 0 || cons.length > 0 || features.length > 0) && (
            <div className="detail-pros-cons">
              <div className="detail-col detail-col--pros">
                <h3 className="detail-col-title">
                  <span className="detail-col-dot detail-col-dot--pro" />
                  What you'll love
                </h3>
                {pros.map((seg, i) => (
                  <div key={i} className="detail-col-item detail-col-item--pro">
                    <span className="detail-col-check">✓</span>{seg.text}
                  </div>
                ))}
                {features.map((f) => (
                  <div key={f} className="detail-col-item detail-col-item--pro">
                    <span className="detail-col-check">✓</span>{f.replaceAll("_", " ")}
                  </div>
                ))}
                {pros.length === 0 && features.length === 0 && (
                  <p className="detail-col-empty">No specific highlights found.</p>
                )}
              </div>

              <div className="detail-col detail-col--cons">
                <h3 className="detail-col-title">
                  <span className="detail-col-dot detail-col-dot--con" />
                  Good to know
                </h3>
                {cons.map((seg, i) => (
                  <div key={i} className="detail-col-item detail-col-item--con">
                    <span className="detail-col-dash">·</span>{seg.text}
                  </div>
                ))}
                {infoItems.map((seg, i) => (
                  <div key={i} className="detail-col-item detail-col-item--info">
                    <span className="detail-col-dash">{ICONS[seg.type]}</span>{seg.text}
                  </div>
                ))}
                {cons.length === 0 && infoItems.length === 0 && (
                  <p className="detail-col-empty">No trade-offs noted.</p>
                )}
              </div>
            </div>
          )}

          {/* Description — rendered as HTML to handle <br/> and **bold** */}
          {listing.description && (
            <section className="detail-section">
              <h2 className="detail-section-title">About this listing</h2>
              <div
                className="detail-description"
                // eslint-disable-next-line react/no-danger
                dangerouslySetInnerHTML={{ __html: renderDescription(listing.description) }}
              />
            </section>
          )}

          {/* Footer meta */}
          <div className="detail-footer-meta">
            <span>Ref: {listing.id}</span>
            {listing.available_from && (
              <span>Available from {listing.available_from}</span>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
