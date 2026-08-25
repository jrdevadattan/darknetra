import type { ReactNode } from "react";

import { ShieldCheck } from "lucide-react";
import Image from "next/image";

import { APP_CONFIG } from "@/config/app-config";

export default function Layout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <main>
      <div className="grid h-dvh justify-center p-2 lg:grid-cols-2">
        <div className="relative order-2 hidden h-full rounded-3xl bg-primary lg:flex">
          <div className="absolute top-10 space-y-2 px-10 text-primary-foreground">
            <ShieldCheck className="size-10" aria-hidden="true" />
            <h1 className="font-medium text-2xl">{APP_CONFIG.name}</h1>
            <p className="max-w-md text-primary-foreground/80 text-sm">
              Evidence-first investigative intelligence with authenticated, case-scoped access.
            </p>
          </div>

          <div className="absolute inset-x-8 bottom-8 overflow-hidden rounded-2xl border border-primary-foreground/10 bg-black/20">
            <Image
              src="/images/darknetra-auth-visual.png"
              alt="DARKNETRA secure intelligence workspace visual"
              width={1536}
              height={1024}
              className="aspect-[3/2] h-auto w-full object-cover opacity-95"
              priority
              unoptimized
            />
          </div>
        </div>
        <div className="relative order-1 flex h-full">{children}</div>
      </div>
    </main>
  );
}
