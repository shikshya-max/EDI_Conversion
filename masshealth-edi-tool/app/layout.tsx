import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MassHealth EDI Eligibility Tool",
  description: "Client-side MassHealth 270 generator and 271 parser",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
