import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IsyMotron · Tu capa de control para IA",
  description: "Una sala de control clara para que la IA proponga y tus equipos decidan.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
