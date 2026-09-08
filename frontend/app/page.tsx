import { Suspense } from "react";
import { Workspace } from "@/components/workspace/workspace";
export default function Home() {
  return (
    <Suspense>
      <Workspace />
    </Suspense>
  );
}
