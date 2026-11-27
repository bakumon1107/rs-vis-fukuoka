import { SITE_URL } from '@/app/lib/site-url';
import { localNavItems } from '@/app/lib/local-gov/site';

/** 地方版のサイトマップ（福岡県版では middleware が /sitemap.xml をここへ書き換える）。国版のページは載せない */
export function GET() {
  const paths = [...localNavItems().map(item => item.href), '/terms', '/privacy'];
  const urls = paths
    .map(path => `  <url>\n    <loc>${SITE_URL}${path}</loc>\n    <changefreq>monthly</changefreq>\n  </url>`)
    .join('\n');
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
  return new Response(xml, { headers: { 'content-type': 'application/xml; charset=utf-8' } });
}
