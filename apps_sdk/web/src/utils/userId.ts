const COOKIE_KEY = "rr_user_id";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];
}

export function getUserId(): string {
  const existing = readCookie(COOKIE_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
  document.cookie = `${COOKIE_KEY}=${id}; max-age=${ONE_YEAR_SECONDS}; path=/; SameSite=Lax`;
  return id;
}
