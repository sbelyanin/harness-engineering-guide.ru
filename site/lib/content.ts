import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { remark } from "remark";
import remarkGfm from "remark-gfm";
import remarkHtml from "remark-html";

const contentDirectory = path.join(process.cwd(), "content");

export interface HeadingItem {
  id: string;
  text: string;
  level: number;
}

export interface ContentItem {
  slug: string;
  title: string;
  description: string;
  author: string;
  category: string;
  date: string;
  originalUrl: string;
  contentHtml: string;
  headings: HeadingItem[];
}

function extractHeadings(markdown: string): HeadingItem[] {
  const headings: HeadingItem[] = [];
  const lines = markdown.split("\n");
  for (const line of lines) {
    const match = line.match(/^(#{2,3})\s+(.+)/);
    if (match) {
      const level = match[1].length;
      const text = match[2].replace(/\*\*/g, "").replace(/`/g, "").trim();
      const id = text
        .toLowerCase()
        .replace(/[^\w\s-]/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .trim();
      headings.push({ id, text, level });
    }
  }
  return headings;
}

function extractMetadataFromContent(markdown: string): {
  title: string;
  description: string;
  author: string;
  category: string;
  date: string;
  originalUrl: string;
} {
  const lines = markdown.split("\n");
  let title = "";
  let description = "";
  let author = "";
  let category = "";
  let date = "";
  let originalUrl = "";

  for (const line of lines) {
    if (!title && line.startsWith("# ")) {
      title = line.replace(/^#\s+/, "").trim();
      continue;
    }
  }

  // Extract first paragraph as description
  const descLines: string[] = [];
  let pastTitle = false;
  for (const line of lines) {
    if (line.startsWith("# ")) { pastTitle = true; continue; }
    if (!pastTitle) continue;
    if (line.startsWith(">") || line.startsWith("---") || line.startsWith("```") || line.startsWith("|")) continue;
    if (line.trim() && !line.startsWith("#")) {
      descLines.push(line.trim());
      if (descLines.length >= 2) break;
    }
    if (line.startsWith("#")) break;
  }
  description = descLines.join(" ").slice(0, 200);

  return { title, description, author, category, date, originalUrl };
}

async function processMarkdown(content: string): Promise<string> {
  const result = await remark()
    .use(remarkGfm)
    .use(remarkHtml, { sanitize: false })
    .process(content);

  let html = result.toString();

  // Add IDs to headings for ToC linking
  html = html.replace(/<h([2-3])>(.*?)<\/h[2-3]>/g, (_, level, text) => {
    const plainText = text.replace(/<[^>]+>/g, "").replace(/&[^;]+;/g, "");
    const id = plainText
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .trim();
    return `<h${level} id="${id}">${text}</h${level}>`;
  });

  // Make external links open in new tab
  html = html.replace(
    /<a href="(https?:\/\/[^"]+)">/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">'
  );

  // Russian typography: NBSP after short prepositions/conjunctions and between numbers+units
  html = typographRussian(html);

  return html;
}

/**
 * Расставляет неразрывные пробелы (NBSP, U+00A0) в русском тексте:
 *  - после одиночных предлогов/союзов (и, а, но, в, с, к, у, о, об, на, по, ...)
 *  - между числом и короткой единицей/словом (10 кг, 5 минут, 128K токенов)
 *
 * Пропускает <code> и <pre> блоки, чтобы не ломать копируемый код.
 */
function typographRussian(html: string): string {
  const NBSP = "\u00A0";
  const preps = [
    "и", "а", "но", "в", "с", "к", "у", "о", "об", "на", "по", "до", "из", "от",
    "за", "для", "или", "что", "как", "не", "ни", "это", "же", "ли", "бы",
    "я", "он", "мы", "вы", "она", "они", "оно",
  ];
  // NB: в JS regex без `u` flag кириллица работает как обычные символы; \b для кириллицы нерабочий,
  // поэтому границы слов выражены явно через пробелы и кириллические классы.
  const prepRe = new RegExp(` (${preps.join("|")}) ([А-Яа-яЁё])`, "g");
  // Число + пробел + кириллическое слово (1-8 букв) + не-кириллица-впереди.
  // Negative lookahead гарантирует, что мы захватили целое слово, а не префикс.
  const numUnitRe = /(\d+) ([А-Яа-яЁё]{1,8})(?![А-Яа-яЁё])/g;

  const applyToText = (text: string): string => {
    let out = text.replace(prepRe, ` $1${NBSP}$2`);
    out = out.replace(numUnitRe, `$1${NBSP}$2$3`);
    return out;
  };

  // Разделяем на <code>/<pre> сегменты (skip) и остальное (apply)
  const segments = html.split(/(<(?:code|pre)\b[^>]*>[\s\S]*?<\/(?:code|pre)>)/gi);
  return segments
    .map((seg, idx) => (idx % 2 === 1 ? seg : applyToText(seg)))
    .join("");
}

export async function getContentBySlug(
  directory: string,
  slug: string
): Promise<ContentItem> {
  const fullPath = path.join(contentDirectory, directory, `${slug}.md`);
  const fileContents = fs.readFileSync(fullPath, "utf8");
  const { data, content } = matter(fileContents);

  const headings = extractHeadings(content);
  const extracted = extractMetadataFromContent(content);
  const contentHtml = await processMarkdown(content);

  return {
    slug,
    title: data.title || extracted.title || slug,
    description: data.description || extracted.description || "",
    author: data.author || extracted.author || "Nexu",
    category: data.category || extracted.category || "",
    date: data.date || extracted.date || "",
    originalUrl: data.originalUrl || extracted.originalUrl || "",
    contentHtml,
    headings,
  };
}

export function getSlugs(directory: string): string[] {
  const dir = path.join(contentDirectory, directory);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((file) => file.endsWith(".md"))
    .map((file) => file.replace(/\.md$/, ""));
}

export async function getAllContent(
  directory: string
): Promise<ContentItem[]> {
  const slugs = getSlugs(directory);
  const items = await Promise.all(
    slugs.map((slug) => getContentBySlug(directory, slug))
  );
  return items;
}
