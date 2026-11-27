import type { Metadata } from 'next';
import { localPageMetadata } from '@/app/lib/local-gov/site';

export const metadata: Metadata = localPageMetadata('データについて');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
