import { redirect } from "next/navigation";

export default function LegacyCleanupRedirect() {
  redirect("/dashboard/cleanup");
}
