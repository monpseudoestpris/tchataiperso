"use client";

import { useEffect } from "react";
import { applyInterfaceTheme, readInterfaceTheme, subscribeInterfaceTheme } from "@/lib/interface-themes";

/** Keep the root palette synchronized even while settings are closed. */
export function InterfaceThemeSync() {
  useEffect(() => {
    applyInterfaceTheme(readInterfaceTheme());
    return subscribeInterfaceTheme(() => {});
  }, []);
  return null;
}
