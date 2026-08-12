import { DesktopOutlined, MoonOutlined, SkinOutlined, SunOutlined } from "@ant-design/icons";
import { Button, Dropdown } from "antd";

import type { ThemeMode } from "../api/types";
import { useThemeMode } from "./themeContext";

const options = [
  { key: "SYSTEM", icon: <DesktopOutlined />, label: "跟随系统" },
  { key: "LIGHT", icon: <SunOutlined />, label: "浅色" },
  { key: "DARK", icon: <MoonOutlined />, label: "深色" },
];

export function ThemeControl() {
  const { mode, setMode } = useThemeMode();
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: options,
        selectable: true,
        selectedKeys: [mode],
        onClick: ({ key }) => setMode(key as ThemeMode),
      }}
      placement="bottomRight"
    >
      <Button icon={<SkinOutlined />} aria-label="外观设置">
        外观
      </Button>
    </Dropdown>
  );
}
