import type { LucideIcon } from "lucide-react";

import {
  DARKNETRA_NAVIGATION,
  canSeeNavigationItem,
  type DarknetraRole,
  type NavigationItem,
} from "@/navigation/darknetra-navigation";

export type NavBadge = "new" | "soon";

export interface NavSubItem {
  id: string;
  title: string;
  url: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
}

interface NavItemBase {
  id: string;
  title: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
}

export interface NavMainLinkItem extends NavItemBase {
  url: string;
  subItems?: never;
}

export interface NavMainParentItem extends NavItemBase {
  subItems: NavSubItem[];
}

export type NavMainItem = NavMainLinkItem | NavMainParentItem;

export interface NavGroup {
  id: number;
  label?: string;
  items: NavMainItem[];
}

const PLAN01_FIXTURE_ROLES: DarknetraRole[] = ["ADMIN"];

function toId(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function toSidebarItem(item: NavigationItem, roles: DarknetraRole[]): NavMainItem {
  const base = { id: toId(item.title), title: item.title, icon: item.icon };
  const visibleChildren = item.children?.filter((child) => canSeeNavigationItem(child, roles)) ?? [];

  if (visibleChildren.length > 0) {
    return {
      ...base,
      subItems: visibleChildren.map((child) => ({
        id: toId(child.title),
        title: child.title,
        url: child.href,
        icon: child.icon,
      })),
    };
  }

  return { ...base, url: item.href };
}

export function buildSidebarItems(roles: DarknetraRole[]): NavGroup[] {
  return [
    {
      id: 1,
      label: "Investigation",
      items: DARKNETRA_NAVIGATION.filter((item) => canSeeNavigationItem(item, roles)).map((item) =>
        toSidebarItem(item, roles),
      ),
    },
  ];
}

export const sidebarItems: NavGroup[] = buildSidebarItems(PLAN01_FIXTURE_ROLES);
