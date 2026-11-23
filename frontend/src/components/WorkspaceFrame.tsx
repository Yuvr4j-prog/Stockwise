"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, subscribeBackendWake } from "@/lib/api";
import { copy } from "@/lib/strings";
import type { Seller } from "@/lib/types";
import { currentIsoWeek } from "@/lib/format";
import { Icon } from "@/components/Icons";

const navLinks = [
  { href: "/products", label: copy.nav.products, icon: "products" as const },
  { href: "/plans", label: copy.nav.plans, icon: "plans" as const },
];

export default function WorkspaceFrame({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [seller, setSeller] = useState<Seller | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [waking, setWaking] = useState(false);
  const [loadError, setLoadError] = useState("");
  const week = currentIsoWeek();

  useEffect(() => {
    let active = true;
    api<Seller>("/auth/me")
      .then((user) => { if (active) setSeller(user); })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) router.replace("/login");
        else { setSeller(null); setLoadError(error instanceof ApiError ? error.message : copy.auth.wakeFailed); }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [router]);

  useEffect(() => subscribeBackendWake(setWaking), []);

  async function signOut() {
    setSigningOut(true);
    try {
      await api<{ message: string }>("/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  if (loading || !seller) {
    return <main className="loading-state" aria-live="polite">
      {waking ? copy.common.wakingUp : loading ? copy.common.loading : loadError ? <><p className="error-message" role="alert">{loadError}</p><button className="button button-secondary" type="button" onClick={() => window.location.reload()}>{copy.common.retry}</button></> : copy.auth.loginTitle}
    </main>;
  }

  return (
    <div className="workspace">
      <a className="skip-link" href="#main-content">{copy.shell.skip}</a>
      <aside className="sidebar" aria-label={copy.shell.pageTitle}>
        <div className="mobile-brand">
          <Link href="/products" className="brand-lockup">
            <span className="brand-mark">{copy.brand.mark}</span>
            <span><span className="brand-name">{copy.brand.name}</span><span className="brand-descriptor">{copy.brand.descriptor}</span></span>
          </Link>
          <span className="mobile-account">{seller.email}</span>
        </div>
        <Link href="/products" className="brand-lockup">
          <span className="brand-mark">{copy.brand.mark}</span>
          <span><span className="brand-name">{copy.brand.name}</span><span className="brand-descriptor">{copy.brand.descriptor}</span></span>
        </Link>
        <p className="side-section-label">{copy.shell.section}</p>
        <nav className="side-nav" aria-label={copy.shell.section}>
          {navLinks.map((item) => {
            const active = item.href === "/products"
              ? pathname === item.href || pathname.startsWith(`${item.href}/`)
              : item.href === "/plans"
                ? pathname === item.href || /^\/plans\/\d+$/.test(pathname)
                : pathname === item.href;
            return (
              <Link key={item.href} href={item.href} className={`nav-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon} className="nav-icon" />{item.label}
              </Link>
            );
          })}
          <Link href="/plans/new" className={`nav-link${pathname === "/plans/new" ? " active" : ""}`} aria-current={pathname === "/plans/new" ? "page" : undefined}>
            <Icon name="plus" className="nav-icon" />{copy.nav.newPlan}
          </Link>
        </nav>
        <div className="sidebar-bottom">
          <div className="account-email" title={seller.email}>{seller.email}</div>
          <button className="sidebar-signout" type="button" onClick={signOut} disabled={signingOut}>
            {signingOut ? copy.common.saving : copy.nav.signOut}
          </button>
        </div>
      </aside>
      <div className="workspace-main">
        <div className="market-strip">
          <div className="market-strip-left"><span className="market-dot" />{copy.shell.currentWeek}<span className="market-week">{week.year} · W{String(week.week).padStart(2, "0")}</span></div>
          <span className="market-currency">{copy.common.currencyNote}</span>
        </div>
        {waking ? <p className="backend-wake workspace-wake" role="status">{copy.common.wakingUp}</p> : null}
        <main id="main-content">{children}</main>
      </div>
    </div>
  );
}
