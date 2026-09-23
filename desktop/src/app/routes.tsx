import type { ReactNode } from "react";
import { AccountPage } from "../pages/AccountPage";
import { AIModulesPage } from "../pages/AIModulesPage";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { CamerasPage } from "../pages/CamerasPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DetectPage } from "../pages/DetectPage";
import { EventsPage } from "../pages/EventsPage";
import { LiveViewPage } from "../pages/LiveViewPage";
import { SettingsPage } from "../pages/SettingsPage";
import { SubscriptionPage } from "../pages/SubscriptionPage";

export interface AppRoute {
  path: string;
  navLabel: string;
  element: ReactNode;
}

/** Single source of truth for the sidebar and the router: every entry here appears in both. */
export const APP_ROUTES: AppRoute[] = [
  { path: "/", navLabel: "Dashboard", element: <DashboardPage /> },
  { path: "/detect", navLabel: "Detect (prototype)", element: <DetectPage /> },
  { path: "/cameras", navLabel: "Cameras", element: <CamerasPage /> },
  { path: "/live-view", navLabel: "Live View", element: <LiveViewPage /> },
  { path: "/events", navLabel: "Events", element: <EventsPage /> },
  { path: "/analytics", navLabel: "Analytics", element: <AnalyticsPage /> },
  { path: "/ai-modules", navLabel: "AI Modules", element: <AIModulesPage /> },
  { path: "/settings", navLabel: "Settings", element: <SettingsPage /> },
  { path: "/account", navLabel: "Account", element: <AccountPage /> },
  { path: "/subscription", navLabel: "Subscription", element: <SubscriptionPage /> },
];
