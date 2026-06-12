import Link from "next/link";

const LINKS = [
  ["/how", "How it works"],
  ["/flow", "Live flow"],
  ["/queue", "Queue"],
  ["/inbox", "Approval inbox"],
  ["/console", "Agent console"],
  ["/analytics", "Analytics"],
  ["/contact", "Talk to me"],
];

export function Nav() {
  return (
    <nav className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-border pb-3 text-sm">
      <Link href="/" className="font-bold tracking-tight">
        Adjuster Zero
      </Link>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} className="text-muted-foreground hover:text-foreground">
          {label}
        </Link>
      ))}
    </nav>
  );
}
