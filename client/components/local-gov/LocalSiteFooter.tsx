import Link from 'next/link';
import { LOCAL_POLICY_LINKS, localNavItems, localSiteConfig } from '@/app/lib/local-gov/site';

/**
 * 地方版の共通フッター（福岡市版「みらい議会＠福岡市」のフッターと同じ形: 主要リンク・規約の並び・免責）。
 * 免責「このサービスは政党チームみらいが運営しているものではありません」は常に出す。
 * チームみらいの案内・寄附・本家の連絡先は出さない。
 */
export function LocalSiteFooter() {
  const { upstream } = localSiteConfig;
  const nav = localNavItems();
  return (
    <footer className="bg-mirai-gradient text-slate-900">
      <div className="mx-auto flex w-full max-w-[640px] flex-col items-center px-6 py-10 text-center">
        <nav aria-label="主要リンク" className="mb-5 w-full">
          <ul className="flex flex-col items-center gap-3 text-[14px] font-semibold text-slate-800 md:flex-row md:justify-center md:gap-5">
            {/* TOP はサンキー図（静的サイトの `/` は移動ページなので直接指す） */}
            <li><Link href={nav[0].href} className="hover:text-slate-900">TOP</Link></li>
            {nav.slice(1).map(item => (
              <li key={item.href}><Link href={item.href} className="hover:text-slate-900">{item.label}</Link></li>
            ))}
          </ul>
        </nav>
        <ul className="mb-5 flex flex-wrap justify-center gap-x-2 gap-y-1 text-[12px] font-semibold text-slate-800">
          {LOCAL_POLICY_LINKS.map((link, index) => (
            <li key={link.href} className="flex items-center gap-2">
              {link.external ? (
                <a href={link.href} target="_blank" rel="noreferrer" className="hover:text-slate-900">{link.label}</a>
              ) : (
                <Link href={link.href} className="hover:text-slate-900">{link.label}</Link>
              )}
              {index < LOCAL_POLICY_LINKS.length - 1 ? <span aria-hidden="true">｜</span> : null}
            </li>
          ))}
        </ul>
        <p className="mb-2 text-[11px] leading-relaxed text-slate-600">
          数字は{localSiteConfig.prefName}が公開している予算書・決算書等をもとにこのサイトで加工したものです。正確な数字は原資料をご確認ください。
          プログラムは「{upstream.name}」（<a href={upstream.repositoryUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2">AGPL-3.0</a>）をもとにしています。
        </p>
        <p className="mb-3 mt-1 text-center text-[11px] text-slate-500">{localSiteConfig.disclaimer}</p>
      </div>
    </footer>
  );
}
