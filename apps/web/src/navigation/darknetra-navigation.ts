import {
  Activity,
  BellRing,
  BookOpenCheck,
  Boxes,
  FileSearch,
  Gauge,
  GitBranch,
  HeartPulse,
  ListChecks,
  Network,
  ScanSearch,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Tags,
  Timeline,
  UserRoundCog,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type DarknetraRole =
  | "ADMIN"
  | "CASE_OWNER"
  | "COLLECTOR"
  | "ANALYST"
  | "REVIEWER"
  | "AUDITOR"
  | "VIEWER";

export interface NavigationItem {
  title: string;
  href: string;
  icon?: LucideIcon;
  roles?: DarknetraRole[];
  children?: NavigationItem[];
}

export interface CaseNavigationItem {
  title: string;
  segment: string;
  icon?: LucideIcon;
}

export function canSeeNavigationItem(item: Pick<NavigationItem, "roles">, roles: DarknetraRole[]): boolean {
  return !item.roles?.length || item.roles.some((role) => roles.includes(role));
}

export const DARKNETRA_NAVIGATION: NavigationItem[] = [
  { title: "Overview", href: "/dashboard", icon: Gauge },
  { title: "Cases", href: "/cases", icon: FileSearch },
  {
    title: "Intelligence",
    href: "/intelligence/trends",
    icon: ScanSearch,
    children: [
      { title: "Emerging Trends", href: "/intelligence/trends", icon: Activity },
      { title: "Source Registry", href: "/intelligence/sources", icon: Boxes },
    ],
  },
  {
    title: "Administration",
    href: "/admin/users",
    icon: UserRoundCog,
    roles: ["ADMIN"],
    children: [
      { title: "Users", href: "/admin/users", icon: Users, roles: ["ADMIN"] },
      { title: "Roles & Permissions", href: "/admin/roles", icon: ShieldCheck, roles: ["ADMIN"] },
      { title: "Taxonomies", href: "/admin/taxonomies", icon: Tags, roles: ["ADMIN"] },
      { title: "System Settings", href: "/admin/settings", icon: Settings, roles: ["ADMIN"] },
    ],
  },
  {
    title: "Audit",
    href: "/audit",
    icon: BookOpenCheck,
    roles: ["ADMIN", "AUDITOR", "REVIEWER"],
  },
  { title: "System Health", href: "/system/health", icon: HeartPulse, roles: ["ADMIN", "AUDITOR"] },
];

export const CASE_NAVIGATION: CaseNavigationItem[] = [
  { title: "Overview", segment: "", icon: Gauge },
  { title: "Evidence", segment: "evidence", icon: FileSearch },
  { title: "Entities", segment: "entities", icon: Boxes },
  { title: "Activity Candidates", segment: "activity", icon: ListChecks },
  { title: "Link Analysis", segment: "links", icon: GitBranch },
  { title: "NarcoGraph", segment: "graph", icon: Network },
  { title: "Timeline", segment: "timeline", icon: Timeline },
  { title: "Alerts", segment: "alerts", icon: BellRing },
  { title: "Reports", segment: "reports", icon: SlidersHorizontal },
];
