'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Check, ExternalLink, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { LOCAL_POLICY_LINKS, localNavItems, localSiteConfig } from '@/app/lib/local-gov/site';

/**
 * 地方版の共通ヘッダー（福岡県版のときだけルートレイアウトが置く）。
 * 見た目は国版の浮島ヘッダーにそろえ（高さ 72px = 上下 12px + 島 48px）、中身は地方版のものだけにする。
 * 本家の AppHeader の部品は import しない（本家のヘッダーが変わっても影響を受けないため）。AI ボタンは置かない。
 */
export function LocalSiteHeader() {
  const pathname = usePathname();
  const items = localNavItems();
  // サンキー図（/local/<gov>）は完全一致、ほかは配下も含めて現在地にする
  const isCurrent = (href: string, index: number) =>
    index === 0 ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header data-pan-disabled="true" className="pointer-events-none absolute inset-x-0 top-0 z-40 px-3 py-3">
      <div className="pointer-events-auto flex h-12 items-center gap-x-3 rounded-2xl border border-mirai-border bg-card px-4 shadow-xs">
        <Link href="/" className="flex h-12 shrink-0 items-center gap-2 transition-opacity hover:opacity-80" aria-label={`${localSiteConfig.siteName} トップ`}>
          <TextLogo />
        </Link>

        <nav aria-label="主要ビュー" className="ml-2 hidden min-w-0 items-center gap-0.5 md:flex">
          {items.map((item, index) => {
            const current = isCurrent(item.href, index);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  'shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs transition-colors',
                  current
                    ? 'bg-mirai-surface-teal font-bold text-primary-accent'
                    : 'font-medium text-mirai-text-subtle hover:bg-mirai-surface hover:text-mirai-text'
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex h-12 shrink-0 items-center">
          <LocalNavMenu items={items} isCurrent={isCurrent} />
        </div>
      </div>
    </header>
  );
}

/** テキストロゴ（福岡市版「みらい議会＠福岡市」と同じ作り: 縦のラベンダーの線 + 名前 + 「＠地域名」） */
function TextLogo() {
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden="true" className="h-8 w-1 rounded-full bg-primary" />
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-bold tracking-normal text-mirai-text">{localSiteConfig.logo.main}</span>
        <span className="mt-0.5 text-[11px] font-medium text-primary-accent">{localSiteConfig.logo.sub}</span>
      </span>
    </span>
  );
}

function LocalNavMenu({ items, isCurrent }: {
  items: ReturnType<typeof localNavItems>;
  isCurrent: (href: string, index: number) => boolean;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="icon"
        onClick={() => setOpen(v => !v)}
        aria-label="ページ切替メニュー"
        aria-expanded={open}
        className="border-mirai-border"
      >
        <Menu />
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden="true" />
          <nav aria-label="全ページ" className="fixed inset-x-3 top-[63px] z-50 max-h-[calc(100dvh-5rem)] w-auto overflow-y-auto rounded-xl border border-mirai-border bg-card p-1.5 text-sm shadow-soft sm:absolute sm:inset-x-auto sm:right-0 sm:top-11 sm:w-56">
            {items.map((item, index) => {
              const current = isCurrent(item.href, index);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  aria-current={current ? 'page' : undefined}
                  className={cn(
                    'flex min-h-9 items-center gap-2 rounded-lg px-2.5 py-1.5 transition-colors',
                    current ? 'bg-mirai-surface-teal font-bold text-primary-accent' : 'font-medium text-mirai-text hover:bg-mirai-surface'
                  )}
                >
                  <span className="min-w-0 flex-1">{item.label}</span>
                  <span className="flex size-3.5 shrink-0 items-center justify-center" aria-hidden="true">
                    {current && <Check className="size-3.5" />}
                  </span>
                </Link>
              );
            })}
            <div className="mt-1 flex flex-col gap-1 border-t border-border px-2.5 pb-1 pt-2 text-[11px] text-mirai-text-muted">
              {LOCAL_POLICY_LINKS.map(link =>
                link.external ? (
                  <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-mirai-text hover:underline">
                    {link.label}<ExternalLink className="size-3" aria-hidden="true" />
                  </a>
                ) : (
                  <Link key={link.href} href={link.href} onClick={() => setOpen(false)} className="hover:text-mirai-text hover:underline">{link.label}</Link>
                )
              )}
            </div>
          </nav>
        </>
      )}
    </div>
  );
}
