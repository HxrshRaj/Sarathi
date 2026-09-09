import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";
import { Providers } from "@/components/providers";
import { UserBadge } from "@/components/user-badge";

export const metadata: Metadata = {
  title: "Sarathi",
  description: "AI software engineering copilot with controlled autonomy",
};

const NAV = [
  ["Dashboard", "/dashboard"],
  ["Repositories", "/repositories"],
  ["Tasks", "/tasks"],
  ["Evaluations", "/evaluations"],
  ["Pull Requests", "/pull-requests"],
  ["Settings", "/settings"],
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Providers>
          <div className="mx-auto flex min-h-screen max-w-[1200px] flex-col">
            <header className="flex items-center justify-between border-b border-border px-6 py-3">
              <div className="flex items-center gap-6">
                <Link href="/dashboard" className="font-mono text-sm font-bold text-accent">
                  ▲ Sarathi
                </Link>
                <nav className="flex gap-4 text-sm text-muted">
                  {NAV.map(([label, href]) => (
                    <Link key={href} href={href} className="hover:text-white">
                      {label}
                    </Link>
                  ))}
                </nav>
              </div>
              <UserBadge />
            </header>
            <main className="flex-1 px-6 py-6">{children}</main>
            <footer className="border-t border-border px-6 py-3 text-xs text-muted">
              Controlled autonomy · sandboxed execution · no fabricated metrics
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
