import { Suspense } from "react";
import { Workspace } from "@/components/workspace/workspace";
export default function LoginPage() {
  return (
    <Suspense>
      <Workspace />
    </Suspense>
  );
}
