import Link from "next/link";

import type { NavCategory } from "./categories";
import styles from "./SiteFooter.module.css";

const jalaliYear = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "Asia/Tehran",
  year: "numeric",
});

/**
 * The one footer for every storefront screen (approved Q1): dark ground, text wordmark
 * («KALÉA», never the image), link groups. The help and legal group (FAQ, contact,
 * privacy, terms) arrives with those pages in batch 5.
 */
export function SiteFooter({ categories }: { categories: NavCategory[] }) {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <span className={styles.wordmark} lang="en">
          KALÉA
        </span>
        <div className={styles.groups}>
          <nav aria-label="فروشگاه" className={styles.group}>
            <span className={styles.groupTitle}>فروشگاه</span>
            {categories.map((category) => (
              <Link key={category.slug} href={`/c/${category.slug}`} className={styles.link}>
                {category.title}
              </Link>
            ))}
            <Link href="/cart" className={styles.link}>
              سبد خرید
            </Link>
          </nav>
        </div>
      </div>
      <div className={styles.legal}>
        <p>© {jalaliYear.format(new Date())} کالیا</p>
      </div>
    </footer>
  );
}
