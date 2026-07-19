import { getAllContent } from "@/lib/content";

export const dynamic = "force-static";

const BASE_URL = "https://harness-guide.com";

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export async function GET() {
  const all = await getAllContent("changelog");
  // Только RU-издание (см. AGENTS.md: префикс ru- отличает от upstream-переводов)
  const ruEntries = all
    .filter((e) => e.slug.startsWith("ru-"))
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));

  const items = ruEntries
    .map((entry) => {
      const url = `${BASE_URL}/changelog#${entry.slug}`;
      const pubDate = entry.date
        ? new Date(entry.date).toUTCString()
        : new Date().toUTCString();
      return `    <item>
      <title>${escapeXml(entry.title)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <description>${escapeXml(entry.description || entry.title)}</description>
      <pubDate>${pubDate}</pubDate>
    </item>`;
    })
    .join("\n");

  const lastBuildDate = ruEntries[0]?.date
    ? new Date(ruEntries[0].date).toUTCString()
    : new Date().toUTCString();

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Harness Engineering Guide (RU) — Changelog</title>
    <link>${BASE_URL}/changelog</link>
    <description>Что нового в русскоязычном издании Harness Engineering Guide: новые статьи, skills, инфраструктурные улучшения.</description>
    <language>ru-ru</language>
    <lastBuildDate>${lastBuildDate}</lastBuildDate>
    <atom:link href="${BASE_URL}/feed.xml" rel="self" type="application/rss+xml" />
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
