import { NextResponse, type NextRequest } from 'next/server';
import { isLocalEdition, routeForLocalEdition } from '@/app/lib/local-gov/site-edition';

/**
 * 地方版（NEXT_PUBLIC_SITE_EDITION=local）のときだけ、国版のページ・API を隠して地方版へ振り分ける。
 * 国版（未設定）のときは何もしない。振り分けの中身は app/lib/local-gov/site-edition.ts。
 * このファイルは本家に無いフォーク独自のもの（本家が作ったら中身を合わせる）。
 */
export function middleware(request: NextRequest) {
  if (!isLocalEdition()) return NextResponse.next();
  const route = routeForLocalEdition(request.nextUrl.pathname);
  switch (route.kind) {
    case 'pass':
      return NextResponse.next();
    case 'rewrite':
      return NextResponse.rewrite(new URL(route.to, request.url));
    case 'redirect':
      return NextResponse.redirect(new URL(route.to, request.url));
    case 'notFound':
      return new NextResponse('Not Found', { status: 404, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  }
}

export const config = {
  // 静的ファイル（国のデータ・国版の OGP）も止めるため、Next.js の内部パス以外はすべて通す
  matcher: ['/((?!_next/).*)'],
};
