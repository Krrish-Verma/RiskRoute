import "leaflet/dist/leaflet.css";
import "@/styles/globals.css";

import type { Metadata } from "next";

import { SiteFooter } from "@/components/site-footer";
import { ProductTelemetry } from "@/components/product-telemetry";

export const metadata: Metadata = {
  title: "RiskRoute",
  description: "Explainable intelligence for comparing modeled route-risk tradeoffs."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ProductTelemetry />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
