import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/workspace/providers";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

export const metadata: Metadata = {
  title: "DARKNETRA",
  description: "Evidence-first narcotics intelligence workspace",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
