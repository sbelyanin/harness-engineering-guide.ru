import { getContentBySlug, getSlugs } from "@/lib/content";
import { guideOrder, guideChapters } from "@/lib/guide-data";
import ArticleLayout from "@/components/ArticleLayout";
import GuideSidebar from "@/components/GuideSidebar";

const BASE_URL = "https://harness-guide.com";

export async function generateStaticParams() {
  return getSlugs("guide").map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const content = await getContentBySlug("guide", slug);
  const url = `${BASE_URL}/guide/${slug}`;
  return {
    title: `${content.title} | Harness Guide`,
    description: content.description,
    authors: content.author ? [{ name: content.author }] : undefined,
    alternates: {
      canonical: url,
    },
    openGraph: {
      title: content.title,
      description: content.description,
      url,
      type: "article",
      publishedTime: content.date || undefined,
      authors: content.author ? [content.author] : undefined,
    },
    twitter: {
      card: "summary_large_image",
      title: content.title,
      description: content.description,
    },
  };
}

export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const content = await getContentBySlug("guide", slug);
  const currentIndex = guideOrder.indexOf(slug);

  const prev =
    currentIndex > 0
      ? { slug: guideOrder[currentIndex - 1], title: guideChapters[guideOrder[currentIndex - 1]] }
      : null;
  const next =
    currentIndex < guideOrder.length - 1
      ? { slug: guideOrder[currentIndex + 1], title: guideChapters[guideOrder[currentIndex + 1]] }
      : null;

  // JSON-LD structured data (Schema.org Article)
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: content.title,
    description: content.description,
    author: {
      "@type": "Person",
      name: content.author || "Harness Engineering Guide",
    },
    publisher: {
      "@type": "Organization",
      name: "Harness Engineering Guide (RU)",
      url: BASE_URL,
    },
    datePublished: content.date || undefined,
    dateModified: content.date || undefined,
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": `${BASE_URL}/guide/${slug}`,
    },
    inLanguage: "ru-RU",
  };

  return (
    <div className="flex gap-8 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-20 pb-16">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <GuideSidebar />
      <div className="flex-1 min-w-0">
        <ArticleLayout
          title={content.title}
          description={content.description}
          author={content.author}
          category={content.category}
          date={content.date}
          originalUrl={content.originalUrl}
          readingTimeMinutes={content.readingTimeMinutes}
          contentHtml={content.contentHtml}
          headings={content.headings}
          prev={prev ? { ...prev, prefix: "/guide" } : undefined}
          next={next ? { ...next, prefix: "/guide" } : undefined}
          embedded
        />
      </div>
    </div>
  );
}
