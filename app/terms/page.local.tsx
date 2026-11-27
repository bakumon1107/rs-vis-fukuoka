import type { Metadata } from 'next';
import { LegalList, LegalParagraph, LegalSectionTitle, LocalLegalPage } from '@/client/components/local-gov/LocalLegalPage';
import { LOCAL_PAGE_PATHS, localPageMetadata, localSiteConfig } from '@/app/lib/local-gov/site';

/**
 * 地方版（静的サイト）の利用規約 `/terms/`。地方版のビルドだけでルートになる（国版は同じフォルダの page.tsx）。
 * 福岡市版「みらい議会＠福岡市」の利用規約（第1〜6条）をもとに、AI 機能の条項を外し、
 * 第2条に AGPL-3.0 と県の公開資料についてのただし書き、第3条に原資料の確認のお願いを足した。
 */
export const metadata: Metadata = localPageMetadata('利用規約', LOCAL_PAGE_PATHS.terms(), {
  description: `${localSiteConfig.siteName}の利用規約`,
});

export default function TermsPage() {
  const { siteName, operator, repositoryUrl, prefName } = localSiteConfig;
  return (
    <LocalLegalPage title="利用規約" description={`${siteName}をご利用いただくにあたっての基本的なルールを定めています。`}>
      <LegalParagraph>
        {siteName}
        （以下「本サービス」といいます。）をご利用いただく場合、以下の規約に同意いただいたものとみなします。
      </LegalParagraph>

      <section className="space-y-4">
        <LegalSectionTitle>第1条（禁止事項）</LegalSectionTitle>
        <LegalParagraph>
          本サービスのユーザー（以下「ユーザー」といいます。）は以下の行為を行ってはなりません。
        </LegalParagraph>
        <LegalList
          items={[
            '法令または公序良俗に反する行為',
            '本サービスの運営を妨げる行為',
            '本サービスの情報を改ざん・加工し、誤解を招く形で利用する行為',
            `${operator.name}（以下「当団体」といいます。）または第三者の権利・利益を侵害する行為`,
            'サーバへの過剰な負荷、システムへの妨害・改ざん・侵入行為',
            '自動化ツール、ボット等による操作',
            'その他、当団体が不適切と判断する一切の行為',
          ]}
        />
      </section>

      <section className="space-y-4">
        <LegalSectionTitle>第2条（知的財産権）</LegalSectionTitle>
        <LegalParagraph>
          本サービスの提供のために用いられるプログラム及びその他データ等のコンテンツ、及び本サービスに掲載されるテキスト、画像、データ等の権利は、当団体または当団体が利用許諾を受けた正当な権利者に帰属します。ユーザーは私的利用の範囲を超えて使用してはなりません。
        </LegalParagraph>
        <LegalParagraph>
          ただし、本サービスのプログラムは GNU Affero General Public License v3.0（AGPL-3.0）で
          <a href={repositoryUrl} target="_blank" rel="noreferrer" className="text-primary-accent underline underline-offset-2">公開しています</a>
          。プログラムの利用・改変・再配布については同ライセンスの定めが本条に優先します。また、本サービスの予算等の数字は{prefName}が公開している資料をもとにしたものであり、前段の定めは、同ライセンスに基づく権利や、{prefName}の公開資料そのものの利用を制限するものではありません。
        </LegalParagraph>
      </section>

      <section className="space-y-4">
        <LegalSectionTitle>第3条（情報に係る不保証）</LegalSectionTitle>
        <LegalParagraph>
          当団体は、本サービスによって提供される情報について、正確性、最新性、完全性、有用性、目的適合性、安全性、合法性、真実性等いかなる事項についても保証しません。
        </LegalParagraph>
        <LegalParagraph>
          本サービスの数字は{prefName}が公開している予算書・決算書等の資料を当団体が加工したものです。正確な内容は原資料をご確認ください。
        </LegalParagraph>
      </section>

      <section className="space-y-4">
        <LegalSectionTitle>第4条（サービスの変更・停止）</LegalSectionTitle>
        <LegalParagraph>
          当団体は、ユーザーへの事前通知なく本サービスの内容を変更・停止できるものとし、それにより生じた損害について一切の責任を負いません。
        </LegalParagraph>
      </section>

      <section className="space-y-4">
        <LegalSectionTitle>第5条（規約の変更）</LegalSectionTitle>
        <LegalParagraph>
          当団体は必要に応じて本規約を変更することができ、変更後にユーザーが本サービスを利用した場合、当該変更に同意したものとみなします。
        </LegalParagraph>
      </section>

      <section className="space-y-4">
        <LegalSectionTitle>第6条（準拠法・管轄）</LegalSectionTitle>
        <LegalParagraph>
          本規約は日本法に準拠し、本サービスに関連して生じる一切の紛争については、
          {operator.jurisdiction}
          を第一審の専属的合意管轄裁判所とします。
        </LegalParagraph>
      </section>
    </LocalLegalPage>
  );
}
