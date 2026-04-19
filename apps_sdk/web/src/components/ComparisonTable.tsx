import { useEffect } from "react";
import type { RankedListingResult } from "../utils/api";
import { resolveImageUrl } from "../utils/api";
import { parseReason, ICONS } from "./ReasonDisplay";

type Props = {
  listings: RankedListingResult[];
  onClose: () => void;
  onOpenDetail: (listingId: string) => void;
  onRemove: (listingId: string) => void;
};

function formatPrice(price: number): string {
  return new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(price);
}

function generateTitle(listing: RankedListingResult["listing"]): string {
  const rooms = listing.rooms ? `${listing.rooms}-room` : null;
  const category = listing.object_category
    ? listing.object_category.charAt(0).toUpperCase() +
      listing.object_category.slice(1).toLowerCase().replace(/_/g, " ")
    : "Property";
  return [rooms, category].filter(Boolean).join(" ");
}

function getHeroImage(listing: RankedListingResult["listing"]): string | null {
  const url = listing.hero_image_url ?? listing.image_urls?.[0] ?? null;
  return url ? resolveImageUrl(url) : null;
}

export default function ComparisonTable({ listings, onClose, onOpenDetail, onRemove }: Props) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  // ── Best-value computations ───────────────────────────────────────────────
  const prices  = listings.map((r) => r.listing.price_chf).filter((p): p is number => p != null);
  const minPrice = prices.length ? Math.min(...prices) : null;

  const roomVals = listings.map((r) => r.listing.rooms).filter((r): r is number => r != null);
  const maxRooms = roomVals.length ? Math.max(...roomVals) : null;

  const areaVals = listings.map((r) => r.listing.living_area_sqm).filter((a): a is number => a != null);
  const maxArea  = areaVals.length ? Math.max(...areaVals) : null;

  const isCheapest  = (p?: number | null) => p != null && p === minPrice && listings.length > 1;
  const isMostRooms = (r?: number | null) => r != null && r === maxRooms && roomVals.length > 1 && maxRooms! > 0;
  const isBiggest   = (a?: number | null) => a != null && a === maxArea  && areaVals.length > 1;

  const n = listings.length;

  return (
    <div className="detail-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="compare-modal" onClick={(e) => e.stopPropagation()}>

        {/* ── Top bar ── */}
        <div className="compare-top-bar">
          <button className="detail-back compare-back-btn" type="button" onClick={onClose}>
            ← Back to results
          </button>
          <h2 className="compare-title">Comparing {n} listing{n !== 1 ? "s" : ""}</h2>
          <div />
        </div>

        {/* ── Sticky column headers (thumbnails + names) ── */}
        <div className="compare-sticky-header">
          <div className="compare-row-label" aria-hidden="true" />
          {listings.map((result) => {
            const hero = getHeroImage(result.listing);
            return (
              <div key={result.listing_id} className="compare-header-col">
                <div className="compare-header-img-wrap">
                  {hero
                    ? <img src={hero} alt="" className="compare-header-img"
                        onError={(e) => { (e.currentTarget as HTMLElement).style.display = "none"; }} />
                    : <div className="compare-header-img compare-header-img--empty" />
                  }
                </div>
                <p className="compare-header-name">{generateTitle(result.listing)}</p>
                <p className="compare-header-location">
                  {[result.listing.city, result.listing.canton].filter(Boolean).join(", ")}
                </p>
                <button
                  type="button"
                  className="compare-remove-btn"
                  onClick={() => onRemove(result.listing_id)}
                  title="Remove from comparison"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>

        {/* ── Scrollable rows ── */}
        <div className="compare-body">

          {/* Price */}
          <CompareRow label="Price">
            {listings.map((r) => (
              <div key={r.listing_id} className={`compare-cell ${isCheapest(r.listing.price_chf) ? "compare-cell--best" : ""}`}>
                {isCheapest(r.listing.price_chf) && <span className="compare-badge compare-badge--price">Lowest</span>}
                <span className="compare-price">
                  {r.listing.price_chf != null ? formatPrice(r.listing.price_chf) : "—"}
                </span>
                {r.listing.offer_type && (
                  <span className="compare-offer-type">
                    {r.listing.offer_type === "RENT" ? "/mo" : "sale"}
                  </span>
                )}
              </div>
            ))}
          </CompareRow>

          {/* Rooms & Area */}
          <CompareRow label="Rooms & Area">
            {listings.map((r) => (
              <div key={r.listing_id} className={`compare-cell ${
                isMostRooms(r.listing.rooms) || isBiggest(r.listing.living_area_sqm) ? "compare-cell--best-alt" : ""
              }`}>
                {isMostRooms(r.listing.rooms) && <span className="compare-badge compare-badge--space">Most rooms</span>}
                {!isMostRooms(r.listing.rooms) && isBiggest(r.listing.living_area_sqm) && (
                  <span className="compare-badge compare-badge--space">Largest</span>
                )}
                <span className="compare-rooms">
                  {r.listing.rooms != null ? `${r.listing.rooms} rooms` : "? rooms"}
                </span>
                {r.listing.living_area_sqm != null && (
                  <span className="compare-area"> · {r.listing.living_area_sqm} m²</span>
                )}
              </div>
            ))}
          </CompareRow>

          {/* Why it matches */}
          <CompareRow label="Why it matches">
            {listings.map((r) => {
              const segs = parseReason(r.reason);
              return (
                <div key={r.listing_id} className="compare-cell compare-cell--badges">
                  {segs.length > 0
                    ? segs.slice(0, 4).map((seg, i) => (
                        <span key={i} className={`reason-badge reason-badge--${seg.type}`}>
                          <span className="reason-icon">{ICONS[seg.type]}</span>
                          {seg.text}
                        </span>
                      ))
                    : <span className="compare-empty">No signals</span>
                  }
                </div>
              );
            })}
          </CompareRow>

          {/* Pros */}
          <CompareRow label="What you'll love">
            {listings.map((r) => {
              const pros = parseReason(r.reason).filter((s) => s.type === "positive");
              const features = (r.listing.features ?? []).slice(0, 4);
              return (
                <div key={r.listing_id} className="compare-cell compare-cell--list">
                  {pros.map((s, i) => (
                    <div key={i} className="compare-list-item compare-list-item--pro">
                      <span className="compare-list-icon">✓</span>{s.text}
                    </div>
                  ))}
                  {features.map((f) => (
                    <div key={f} className="compare-list-item compare-list-item--pro">
                      <span className="compare-list-icon">✓</span>{f.replaceAll("_", " ")}
                    </div>
                  ))}
                  {pros.length === 0 && features.length === 0 && (
                    <span className="compare-empty">None noted</span>
                  )}
                </div>
              );
            })}
          </CompareRow>

          {/* Cons */}
          <CompareRow label="Good to know">
            {listings.map((r) => {
              const cons = parseReason(r.reason).filter(
                (s) => s.type === "negative" || s.type === "moderate",
              );
              return (
                <div key={r.listing_id} className="compare-cell compare-cell--list">
                  {cons.map((s, i) => (
                    <div key={i} className="compare-list-item compare-list-item--con">
                      <span className="compare-list-icon compare-list-icon--con">·</span>{s.text}
                    </div>
                  ))}
                  {cons.length === 0 && <span className="compare-empty">No trade-offs</span>}
                </div>
              );
            })}
          </CompareRow>

          {/* Actions */}
          <CompareRow label="">
            {listings.map((r) => (
              <div key={r.listing_id} className="compare-cell compare-cell--actions">
                <button
                  type="button"
                  className="compare-view-btn"
                  onClick={() => { onClose(); onOpenDetail(r.listing_id); }}
                >
                  View details →
                </button>
              </div>
            ))}
          </CompareRow>

        </div>
      </div>
    </div>
  );
}

function CompareRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="compare-row">
      <div className="compare-row-label">{label}</div>
      {children}
    </div>
  );
}
