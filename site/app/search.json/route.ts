import { getSearchIndex } from "@/lib/content";

export const dynamic = "force-static";

export async function GET() {
  const index = await getSearchIndex();
  return new Response(JSON.stringify(index), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
