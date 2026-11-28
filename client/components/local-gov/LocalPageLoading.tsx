import LoadingSpinner from '@/client/components/LoadingSpinner';
import { LocalHeaderSpacer } from '@/client/components/local-gov/LocalHeaderSpacer';

/**
 * 地方版の画面の読み込み中（表示専用）。
 * 画面全体を覆う幕（LoadingSpinner の fullscreen）だと、開くたびに「幕 → 本来の画面」と入れ替わり、別のページへ飛ばされたように見えた。
 * 本来の画面と同じ背景・ヘッダーの下の余白のまま、中身の場所に「読み込み中」を出す（フッターは画面の下に押し出す）
 */
export function LocalPageLoading() {
  return (
    <div className="min-h-screen bg-mirai-surface">
      <LocalHeaderSpacer />
      <LoadingSpinner className="h-[60vh]" />
    </div>
  );
}
