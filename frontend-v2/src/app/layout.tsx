import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Agentic Form Generator",
  description: "AI-powered form building.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full overflow-hidden">
      <body className={`${inter.className} h-full m-0 p-0 flex flex-col overflow-hidden bg-white`}>
        <Navbar />
        <div className="flex-1 flex overflow-hidden w-full h-full m-0 p-0">
          {children}
        </div>
      </body>
    </html>
  );
}

