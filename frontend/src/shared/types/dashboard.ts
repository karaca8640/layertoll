// NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026. Original work: XPack MCP Marketplace (Apache-2.0).
export enum TabKey {
  // LayerToll (OKX Dev Day 2026)
  AGENT_SERVICES = "agent-services",
  SETTLEMENT = "settlement",
  CONSOLE = "console",
  MCP_SERVICES = "mcp-services",
  USER_MANAGEMENT = "user-management",
  RESOURCE_GROUP = "resource-group",
  REVENUE_MANAGEMENT = "revenue-management",
  PAYMENT_CHANNELS = "payment-channels",
  LOGIN_SETTINGS = "login-settings",
  SYSTEM_SETTINGS = "system-settings",
  OVERVIEW = "overview",
  WALLET = "wallet",
  ACCOUNT = "account",
  USER_ACCOUNT = "user-account",
}

export interface SidebarSubItem {
  key: string;
  label: string;
  description?: string;
}

export interface SidebarItem {
  key: TabKey | string;
  icon: React.ReactNode;
  label: string;
  description?: string;
  subItems?: SidebarSubItem[];
}

export interface SidebarItemWithActive extends SidebarItem {
  isExpanded?: boolean;
}

export interface DashboardSidebarProps {
  activeTab: TabKey | string;
  activeSubTab?: string;
  onTabNavigate?: (tab: TabKey | string, subTab?: string) => void;
  onLogout: () => void;
  bottomPanel?: React.ReactNode;
  sidebarItems: SidebarItem[];
  userProfilePanel?: React.ReactNode;
  langNode?: React.ReactNode;
}
