import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Aegis — Private Personal Search & Research Engine',
  description: 'Self-hosted, local-first personal search engine powered by hybrid vector BM25 retrieval and private AI.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-indigo-500 selection:text-white">
        {children}
      </body>
    </html>
  )
}
