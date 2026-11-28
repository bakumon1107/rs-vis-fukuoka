import type { Metadata } from 'next';
import { LOCAL_PAGE_PATHS, localPageMetadata } from '@/app/lib/local-gov/site';

export const metadata: Metadata = localPageMetadata('基金と財政の指標',LOCAL_PAGE_PATHS.funds());

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
