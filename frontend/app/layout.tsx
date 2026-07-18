import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Research Paper Replicator",
  description: "Multi-agent implementation replication platform for Computer Vision research papers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

