import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ISyMotron // Capability Fabric",
  description: "A soft-neon control room for local AI authority.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
