import { loadNavCategories } from "@/components/layout/categories";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";

// Storefront pages show live prices and stock: never prerender them at build time.
export const dynamic = "force-dynamic";

export default async function ShopLayout({ children }: { children: React.ReactNode }) {
  const categories = await loadNavCategories();
  return (
    <>
      <a href="#main" className="skip-link">
        رفتن به محتوای اصلی
      </a>
      <SiteHeader categories={categories} />
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <SiteFooter categories={categories} />
    </>
  );
}
