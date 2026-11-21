import type { Metadata } from "next";
import "@fontsource-variable/source-serif-4";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource-variable/noto-sans-devanagari";
import "@fontsource-variable/noto-serif-devanagari";
import "./globals.css";
import { copy } from "@/lib/strings";

export const metadata: Metadata = {
  title: copy.brand.name,
  description: copy.products.description,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
