import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeControl } from "./ThemeControl";
import { ThemeProvider } from "./ThemeProvider";

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("supports system, light and dark modes without touching research data", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemeControl />
      </ThemeProvider>,
    );
    const appearance = screen.getByLabelText("外观设置");
    expect(appearance).toBeInTheDocument();
    await user.click(appearance);
    await user.click(screen.getByText("深色"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("quantlab.theme-mode")).toBe("DARK");
    await user.click(appearance);
    await user.click(screen.getByText("浅色"));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
