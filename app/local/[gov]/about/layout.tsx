import type { Metadata } from 'next';
import { LOCAL_PAGE_PATHS, localPageMetadata } from '@/app/lib/local-gov/site';

export const metadata: Metadata = localPageMetadata('データについて', LOCAL_PAGE_PATHS.about());

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
