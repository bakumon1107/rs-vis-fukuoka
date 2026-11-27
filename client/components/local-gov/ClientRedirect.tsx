'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** 表示されたらすぐ `href` へ移る（静的サイトのトップ用。meta refresh の補助。href は basePath なしで渡す） */
export function ClientRedirect({ href }: { href: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(href);
  }, [router, href]);
  return null;
}
