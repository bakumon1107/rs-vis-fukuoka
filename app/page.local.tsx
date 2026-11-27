import type { Metadata } from 'next';
import Link from 'next/link';
import { localGovId, withBasePath } from '@/app/lib/local-gov/site-edition';
import { localSiteConfig } from '@/app/lib/local-gov/site';
import { LocalHeaderSpacer } from '@/client/components/local-gov/LocalHeaderSpacer';

/**
 * 地方版（静的サイト）のトップ `/`。自治体のサンキー図へ移るだけの静的ページ。
 * redirect() は静的書き出しでは JavaScript でしか移らないページになるので使わず（設計書 10.6）、
 * meta refresh（0 秒）と見えるリンクで移す。meta は React が head に移す（正しい HTML。JavaScript の有無・
 * スクリプトの読み込みの失敗に関係なく移る）。
 * クライアントでのソフトな移動（router.replace）は足さない: 同じ文書のまま移るので meta refresh のタイマーが残り、
 * 移った先を読み直してしまう（レビューで見つけた）
 */
const target = `/local/${localGovId()}/`;

export const metadata: Metadata = {
  title: { absolute: localSiteConfig.siteName },
};

export default function Home() {
  return (
    <div className="min-h-[60vh] bg-background text-mirai-text">
      <meta httpEquiv="refresh" content={`0; url=${withBasePath(target)}`} />
      <LocalHeaderSpacer />
      <main className="px-4 py-8 text-center">
        <p className="text-sm">
          <Link href={target} className="font-bold text-primary-accent underline underline-offset-4">
            {localSiteConfig.prefName}の予算のサンキー図へ移動します
          </Link>
        </p>
      </main>
    </div>
  );
}
