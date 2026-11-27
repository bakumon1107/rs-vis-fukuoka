import type { Metadata } from 'next';
import Link from 'next/link';
import { localGovId, withBasePath } from '@/app/lib/local-gov/site-edition';
import { localSiteConfig } from '@/app/lib/local-gov/site';
import { ClientRedirect } from '@/client/components/local-gov/ClientRedirect';
import { LocalHeaderSpacer } from '@/client/components/local-gov/LocalHeaderSpacer';

/**
 * 地方版（静的サイト）のトップ `/`。自治体のサンキー図へ移るだけの静的ページ。
 * redirect() は静的書き出しでは JavaScript でしか移らないページになるので使わず（設計書 10.6）、
 * meta refresh（JavaScript なしでも移る）・見えるリンク・クライアントでの replace の 3 つで移す。
 */
const target = `/local/${localGovId()}/`;

export const metadata: Metadata = {
  title: { absolute: localSiteConfig.siteName },
};

export default function Home() {
  return (
    <div className="min-h-[60vh] bg-background text-mirai-text">
      {/* JavaScript があれば ClientRedirect がすぐ移す。meta refresh は JavaScript なしのときだけ（noscript の中）。
          外に置くと、ClientRedirect の移動（同じ文書のままのソフトな移動）の後に meta refresh のタイマーが残り、
          移った先のサンキー図を読み直してしまう */}
      <noscript>
        <meta httpEquiv="refresh" content={`0; url=${withBasePath(target)}`} />
      </noscript>
      <ClientRedirect href={target} />
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
