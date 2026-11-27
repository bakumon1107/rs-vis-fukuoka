/**
 * 共通ヘッダー（国版の AppHeader・地方版の LocalSiteHeader。どちらも高さ 72px で画面上部に重なる）の下の余白。
 * 本家の AppHeader の「プロバイダが無いと余白だけ出す」挙動に頼らないよう、地方版の画面はこれを置く。
 */
export function LocalHeaderSpacer() {
  return <div aria-hidden="true" className="h-[72px] shrink-0" />;
}
