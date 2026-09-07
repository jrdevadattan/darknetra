"use client";

import { IconButton } from "@chakra-ui/react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme !== "light";
  return <IconButton aria-label="Toggle color theme" size="sm" variant="ghost" colorPalette="teal" onClick={() => setTheme(isDark ? "light" : "dark")}>
    {isDark ? <Sun size={16} /> : <Moon size={16} />}
  </IconButton>;
}
