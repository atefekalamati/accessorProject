"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { cartUnitCount, useCart } from "@/api/queries/cart";
import { BagIcon, CloseIcon, MenuIcon, UserIcon } from "@/components/ui/icons";
import { toPersianDigits } from "@/lib/format";

import type { NavCategory } from "./categories";
import { Logo } from "./Logo";
import styles from "./SiteHeader.module.css";

/**
 * The one header for every storefront screen (approved Q1): category nav, logo, account
 * and cart. Search is post-MVP and hidden. On phones the nav moves into a menu panel.
 */
export function SiteHeader({ categories }: { categories: NavCategory[] }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);
  const menuId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);

  // Close the phone menu after navigating.
  if (menuPath !== pathname) {
    setMenuPath(pathname);
    setMenuOpen(false);
  }

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const isCurrent = (slug: string) => pathname === `/c/${slug}`;

  return (
    <header className={styles.header}>
      <div className={styles.bar}>
        <button
          ref={menuButton}
          type="button"
          className={`${styles.iconButton} ${styles.menuButton}`}
          aria-label={menuOpen ? "بستن منو" : "منو"}
          aria-expanded={menuOpen}
          aria-controls={menuId}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <CloseIcon /> : <MenuIcon />}
        </button>

        <nav aria-label="دسته‌بندی‌ها" className={styles.nav}>
          {categories.map((category) => (
            <Link
              key={category.slug}
              href={`/c/${category.slug}`}
              aria-current={isCurrent(category.slug) ? "page" : undefined}
              className={styles.navLink}
            >
              {category.title}
            </Link>
          ))}
        </nav>

        <div className={styles.logo}>
          <Logo />
        </div>

        <div className={styles.actions}>
          <Link
            href="/account/orders"
            aria-label="حساب کاربری"
            className={`${styles.iconButton} ${styles.account}`}
          >
            <UserIcon />
          </Link>
          <CartButton />
        </div>
      </div>

      <div id={menuId} className={styles.menu} hidden={!menuOpen}>
        <nav aria-label="منوی اصلی" className={styles.menuNav}>
          {categories.map((category) => (
            <Link
              key={category.slug}
              href={`/c/${category.slug}`}
              aria-current={isCurrent(category.slug) ? "page" : undefined}
              className={styles.menuLink}
            >
              {category.title}
            </Link>
          ))}
          <Link href="/account/orders" className={styles.menuLink}>
            حساب کاربری
          </Link>
        </nav>
      </div>
    </header>
  );
}

function CartButton() {
  const { data } = useCart();
  const count = cartUnitCount(data);
  const label = `سبد خرید، ${toPersianDigits(count)} کالا`;
  return (
    <Link href="/cart" aria-label={label} className={`${styles.iconButton} ${styles.cart}`}>
      <BagIcon />
      {count > 0 ? (
        <span className={styles.badge} aria-hidden="true">
          {toPersianDigits(count)}
        </span>
      ) : null}
    </Link>
  );
}
