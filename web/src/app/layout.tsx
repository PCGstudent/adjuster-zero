import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adjuster Zero",
  description: "An autonomous claims department with a paper trail.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
