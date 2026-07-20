import { MetadataRoute } from "next";
import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { guideOrder } from "@/lib/guide-data";
import { getSlugs } from "@/lib/content";

export const dynamic = "force-static";

const BASE_URL = "https://harness-guide.com";

/** Возвращает дату последней модификации статьи:
 *  - frontmatter.date если есть (ISO-строка),
 *  - иначе mtime файла на диске. */
function lastModifiedFor(slug: string): string {
  // Чтение напрямую из корня репо (sync-content уже отработал к моменту build'а)
  const rootPath = path.join(process.cwd(), "..", "..", "guide", `${slug}.md`);
  const contentPath = path.join(process.cwd(), "content", "guide", `${slug}.md`);
  const filePath = fs.existsSync(rootPath) ? rootPath : contentPath;

  try {
    const raw = fs.readFileSync(filePath, "utf8");
    const { data } = matter(raw);
    if (data.date) {
      const d = data.date instanceof Date ? data.date : new Date(data.date as string);
      return d.toISOString();
    }
  } catch {
    // ignore — fallback ниже
  }
  try {
    return fs.statSync(filePath).mtime.toISOString();
  } catch {
    return new Date().toISOString();
  }
}

export default function sitemap(): MetadataRoute.Sitemap {
  const routes: MetadataRoute.Sitemap = [
    { url: BASE_URL, lastModified: new Date().toISOString(), changeFrequency: "weekly", priority: 1.0 },
    { url: `${BASE_URL}/changelog`, lastModified: new Date().toISOString(), changeFrequency: "weekly", priority: 0.8 },
    { url: `${BASE_URL}/community`, lastModified: new Date().toISOString(), changeFrequency: "monthly", priority: 0.6 },
    { url: `${BASE_URL}/metrics`, lastModified: new Date().toISOString(), changeFrequency: "weekly", priority: 0.5 },
  ];

  for (const slug of guideOrder) {
    routes.push({
      url: `${BASE_URL}/guide/${slug}`,
      lastModified: lastModifiedFor(slug),
      changeFrequency: "monthly",
      priority: 0.7,
    });
  }

  // Changelog-записи (если есть SSG-страницы под них)
  for (const slug of getSlugs("changelog")) {
    routes.push({
      url: `${BASE_URL}/changelog#${slug}`,
      lastModified: new Date().toISOString(),
      priority: 0.4,
    });
  }

  return routes;
}
