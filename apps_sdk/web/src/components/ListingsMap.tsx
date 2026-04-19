import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RankedListingResult } from "../utils/api";

type ListingsMapProps = {
  results: RankedListingResult[];
  selectedId: string | null;
  selectedListing: RankedListingResult | null;
  onSelect: (listingId: string) => void;
};

const MAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-positron": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO',
    },
  },
  layers: [
    {
      id: "carto-positron-layer",
      type: "raster",
      source: "carto-positron",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

// Switzerland bounding box
const SWITZERLAND_BOUNDS: maplibregl.LngLatBoundsLike = [
  [5.96, 45.82],
  [10.49, 47.81],
];

function formatPinPrice(price?: number | null): string {
  if (price == null) return "—";
  return new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(price);
}

export default function ListingsMap({
  results,
  selectedId,
  selectedListing,
  onSelect,
}: ListingsMapProps) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  const coordinateResults = results.filter(
    (r) =>
      typeof r.listing.latitude === "number" &&
      typeof r.listing.longitude === "number",
  );

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    mapRef.current = new maplibregl.Map({
      container: mapContainerRef.current,
      style: MAP_STYLE,
      center: [8.23, 46.82],
      zoom: 7,
      attributionControl: false,
    });

    mapRef.current.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );

    mapRef.current.on("load", () => {
      mapRef.current!.fitBounds(SWITZERLAND_BOUNDS, {
        padding: { top: 40, bottom: 100, left: 40, right: 40 },
        duration: 0,
      });
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    const map = mapRef.current;
    if (!map) return;

    coordinateResults.forEach((result) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `map-pin ${selectedId === result.listing_id ? "selected" : ""}`;
      el.textContent = formatPinPrice(result.listing.price_chf);
      el.onclick = () => onSelect(result.listing_id);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([result.listing.longitude!, result.listing.latitude!])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>${result.listing.title}</strong><br/>${result.listing.city ?? ""}`,
          ),
        )
        .addTo(map);

      markersRef.current.push(marker);
    });

    if (coordinateResults.length) {
      const bounds = new maplibregl.LngLatBounds();
      coordinateResults.forEach((r) =>
        bounds.extend([r.listing.longitude!, r.listing.latitude!]),
      );
      map.fitBounds(bounds, { padding: 80, maxZoom: 13, duration: 400 });
    }
  }, [coordinateResults, onSelect, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedListing) return;
    const { latitude, longitude } = selectedListing.listing;
    if (typeof latitude === "number" && typeof longitude === "number") {
      map.easeTo({
        center: [longitude, latitude],
        zoom: Math.max(map.getZoom(), 12),
        duration: 500,
      });
    }
  }, [selectedListing]);

  return <div ref={mapContainerRef} className="map-container" />;
}
