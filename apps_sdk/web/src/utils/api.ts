import { API_BASE_URL } from "../config";

export type ListingData = {
  id: string;
  title: string;
  description?: string | null;
  city?: string | null;
  canton?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_urls?: string[] | null;
  hero_image_url?: string | null;
  price_chf?: number | null;
  rooms?: number | null;
  living_area_sqm?: number | null;
  available_from?: string | null;
  features?: string[];
  offer_type?: string | null;
  object_category?: string | null;
};

export type RankedListingResult = {
  listing_id: string;
  score: number;
  reason: string;
  listing: ListingData;
};

export type SearchResponse = {
  listings: RankedListingResult[];
  meta?: Record<string, unknown>;
};

export type InteractionEventType = "click" | "favorite" | "hide" | "view" | "image_browse";

export async function searchListings(
  query: string,
  userId: string,
  limit = 25,
  offset = 0,
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE_URL}/listings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, user_id: userId, limit, offset }),
  });
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  return res.json() as Promise<SearchResponse>;
}

export function resolveImageUrl(url: string): string {
  return url.startsWith("/") ? `${API_BASE_URL}${url}` : url;
}

export function logInteraction(
  userId: string,
  listingId: string,
  eventType: InteractionEventType,
  query?: string,
): void {
  fetch(`${API_BASE_URL}/users/${userId}/interactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      listing_id: listingId,
      event_type: eventType,
      query,
      user_id: userId,
    }),
  }).catch(() => {});
}
