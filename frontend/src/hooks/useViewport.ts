import { useEffect, useState } from "react";

export type ViewportMode = "mobile" | "tablet" | "desktop";

function currentMode(): ViewportMode {
  if (window.matchMedia("(max-width: 767px)").matches) return "mobile";
  if (window.matchMedia("(max-width: 1199px)").matches) return "tablet";
  return "desktop";
}

export function useViewportMode(): ViewportMode {
  const [mode, setMode] = useState<ViewportMode>(currentMode);

  useEffect(() => {
    const mobile = window.matchMedia("(max-width: 767px)");
    const tablet = window.matchMedia("(max-width: 1199px)");
    const update = () => setMode(mobile.matches ? "mobile" : tablet.matches ? "tablet" : "desktop");
    mobile.addEventListener("change", update);
    tablet.addEventListener("change", update);
    return () => {
      mobile.removeEventListener("change", update);
      tablet.removeEventListener("change", update);
    };
  }, []);

  return mode;
}
