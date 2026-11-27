import type { ReactNode } from 'react';
import { LocalHeaderSpacer } from './LocalHeaderSpacer';

/**
 * 地方版の利用規約・プライバシーポリシーの共通レイアウト（福岡市版の LegalPageLayout と同じ並び: 見出し・説明・本文）。
 * 本家の components/legal/LegalDocument はチームみらいの連絡先を出すので使わない。
 */
export function LocalLegalPage({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-mirai-text">
      <LocalHeaderSpacer />
      <main className="px-4 pb-16 pt-4 sm:px-6">
        <article className="mx-auto max-w-3xl">
          <header className="rounded-2xl bg-mirai-gradient p-6 sm:p-8">
            <h1 className="text-2xl font-bold tracking-normal sm:text-3xl">{title}</h1>
            <p className="mt-2 text-sm leading-relaxed text-mirai-text-subtle">{description}</p>
          </header>
          <div className="mt-8 space-y-10">{children}</div>
        </article>
      </main>
    </div>
  );
}

export function LegalSectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-lg font-bold">{children}</h2>;
}

export function LegalParagraph({ children }: { children: ReactNode }) {
  return <p className="text-sm leading-relaxed">{children}</p>;
}

export function LegalList({ items }: { items: readonly ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
      {items.map((item, index) => <li key={index}>{item}</li>)}
    </ul>
  );
}
