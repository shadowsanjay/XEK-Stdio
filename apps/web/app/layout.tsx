import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "XEK STUDIO — One Prompt. An Entire Movie.", description: "Self-hosted AI film production" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
