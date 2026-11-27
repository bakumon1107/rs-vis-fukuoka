import { SITE_URL } from '@/app/lib/site-url';

/**
 * 地方版の robots.txt（福岡県版では middleware が /robots.txt をここへ書き換える）。
 * 各画面は metadata で noindex にしている（数字の確認が済むまで検索エンジンに載せない）。ここではクロールは止めない
 * （止めると noindex を読めず、URL だけが載ることがあるため）。
 */
export function GET() {
  const body = ['User-agent: *', 'Allow: /', 'Disallow: /api/', '', `Sitemap: ${SITE_URL}/sitemap.xml`, ''].join('\n');
  return new Response(body, { headers: { 'content-type': 'text/plain; charset=utf-8' } });
}
