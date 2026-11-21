import Link from "next/link";

import { loadNavCategories } from "@/components/layout/categories";

import styles from "./page.module.css";

/** Placeholder home for batch 1 (shell only); batch 2 replaces it with HomeAlt. */
export default async function HomePage() {
  const categories = await loadNavCategories();
  return (
    <div className="container">
      <section className={styles.hero} aria-labelledby="home-title">
        <h1 id="home-title" className="t-heading-1">
          کالیا
        </h1>
        <p className={styles.lead}>انتخاب‌شده با دقت، فروخته‌شده مستقیم.</p>
        {categories.length > 0 ? (
          <ul className={styles.links}>
            {categories.map((category) => (
              <li key={category.slug}>
                <Link href={`/c/${category.slug}`} className={styles.link}>
                  {category.title}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
