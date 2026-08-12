import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PairingGate } from "./PairingGate";
import { SettingsDrawer } from "./SettingsDrawer";

describe("LAN settings", () => {
  it("shows the private URL, pairing code and firewall boundary only in active LAN mode", () => {
    render(
      <SettingsDrawer
        open
        settings={{ theme: "SYSTEM", lan_enabled: true }}
        runtime={{
          mode: "LAN",
          authenticated: true,
          pairing_required: true,
          lan_url: "http://192.168.1.20:3000/",
          pairing_code: "314159",
        }}
        saving={false}
        onClose={vi.fn()}
        onLANChange={vi.fn()}
      />,
    );

    expect(screen.getByText("http://192.168.1.20:3000/")).toBeVisible();
    expect(screen.getByText("314159")).toBeVisible();
    expect(screen.getByText(/只允许专用网络/)).toBeVisible();
    expect(document.querySelector("canvas")).toBeInTheDocument();
  });

  it("marks a changed LAN preference as requiring restart", () => {
    render(
      <SettingsDrawer
        open
        settings={{ theme: "SYSTEM", lan_enabled: true }}
        runtime={{
          mode: "DESKTOP",
          authenticated: true,
          pairing_required: false,
          lan_url: null,
          pairing_code: null,
        }}
        saving={false}
        onClose={vi.fn()}
        onLANChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/下次启动 QuantLab 时生效/)).toBeVisible();
    expect(screen.queryByText(/本次配对码/)).not.toBeInTheDocument();
  });

  it("validates and submits exactly six pairing digits", async () => {
    const user = userEvent.setup();
    const onPair = vi.fn();
    render(<PairingGate loading={false} error={null} onPair={onPair} />);

    await user.type(screen.getByLabelText("配对码"), "123");
    await user.click(screen.getByRole("button", { name: /连\s*接/ }));
    expect(await screen.findByText("配对码必须是 6 位数字")).toBeVisible();
    expect(onPair).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("配对码"));
    await user.type(screen.getByLabelText("配对码"), "654321");
    await user.click(screen.getByRole("button", { name: /连\s*接/ }));
    expect(onPair).toHaveBeenCalledOnce();
    expect(onPair).toHaveBeenCalledWith("654321");
  });
});
