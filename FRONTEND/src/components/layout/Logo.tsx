import Image from "next/image";
import Link from "next/link";

import logo from "../../../docs/design/brand/kalea-ribbon.png";

import styles from "./Logo.module.css";

/** The ribbon logo, always a link home (HANDOFF §2). Height is set by the variant. */
export function Logo({ variant = "header" }: { variant?: "header" | "login" }) {
  return (
    <Link href="/" aria-label="کالیا — صفحه‌ی اصلی" className={styles.link}>
      <Image
        src={logo}
        alt="Kaléa"
        className={variant === "login" ? styles.login : styles.header}
        sizes="(max-width: 767px) 125px, 166px"
        preload
      />
    </Link>
  );
}
