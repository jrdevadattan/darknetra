import type { Metadata } from "next";
import "./globals.css";
import { Provider } from "@/components/provider";

export const metadata: Metadata = { title: "DARKNETRA", description: "Evidence-first narcotics intelligence workspace" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><body><Provider>{children}</Provider></body></html>;
}
