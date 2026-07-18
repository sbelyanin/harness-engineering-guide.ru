import { MetadataRoute } from "next";
import { guideOrder } from "@/lib/guide-data";

export const dynamic = "force-static";

const BASE_URL = "https://harness-guide.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes: MetadataRoute.Sitemap = [
    { url: BASE_URL, lastModified: new Date().toISOString() },
    { url: `${BASE_URL}/changelog`, lastModified: new Date().toISOString() },
  ];

  for (const slug of guideOrder) {
    routes.push({
      url: `${BASE_URL}/guide/${slug}`,
      lastModified: new Date().toISOString(),
    });
  }

  return routes;
}
