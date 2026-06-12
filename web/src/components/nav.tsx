import Link from "next/link";

export function Nav() {
  return (
    <nav className="mb-6 flex items-center gap-6 border-b border-border pb-3 text-sm">
      <Link href="/" className="font-bold tracking-tight">
        Adjuster Zero
      </Link>
      <Link href="/" className="text-muted-foreground hover:text-foreground">
        Queue
      </Link>
      <Link href="/inbox" className="text-muted-foreground hover:text-foreground">
        Approval inbox
      </Link>
      <Link href="/console" className="text-muted-foreground hover:text-foreground">
        Agent console
      </Link>
    </nav>
  );
}
