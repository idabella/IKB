import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Factory AI Brain — Industrial Knowledge System",
  description:
    "Real-time industrial monitoring, knowledge graph exploration, and AI-powered diagnostics",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
