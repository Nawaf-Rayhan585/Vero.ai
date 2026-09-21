import type { AppEvent, EventType } from "../api/types";

export type EventTone = "neutral" | "success" | "warning" | "danger";

export interface EventDescription {
  /** The short label, shown as a badge. */
  title: string;
  /** What it concerned: the line or zone, the text read, the error. */
  detail: string;
  tone: EventTone;
}

const READ_LABELS: Record<string, string> = { qr: "QR code read", barcode: "Barcode read", ocr: "Text read" };

function who(category: string | null): string {
  return category === "vehicle" ? "Vehicle" : "Person";
}

export function describeEvent(event: AppEvent): EventDescription {
  switch (event.event_type) {
    case "line_crossed":
      return {
        title: `${who(event.category)} crossed ${event.direction === "out" ? "out" : "in"}`,
        detail: event.subject_name ? `Line: ${event.subject_name}` : "",
        tone: "neutral",
      };
    case "zone_entered":
      return { title: `${who(event.category)} entered zone`, detail: event.subject_name ?? "", tone: "neutral" };
    case "zone_exited":
      return { title: `${who(event.category)} left zone`, detail: event.subject_name ?? "", tone: "neutral" };
    case "read": {
      const symbology = event.category === "ocr" ? "" : event.detail ? ` (${event.detail})` : "";
      return {
        title: READ_LABELS[event.category ?? ""] ?? "Read",
        detail: `${event.value ?? ""}${symbology}`,
        tone: "neutral",
      };
    }
    case "tracking_started":
      return { title: "Tracking started", detail: "", tone: "success" };
    case "tracking_stopped":
      return { title: "Tracking stopped", detail: event.value ?? "", tone: "neutral" };
    case "tracking_error":
      return { title: "Tracking error", detail: event.value ?? "", tone: "danger" };
    case "tracking_reconnecting":
      return { title: "Connection lost, reconnecting", detail: "", tone: "warning" };
    case "tracking_resumed":
      return { title: "Camera reconnected", detail: "", tone: "success" };
  }
}

/** The filter groups on the Events page, each one or more backend event types. */
export const EVENT_FILTER_GROUPS: { id: string; label: string; types: EventType[] }[] = [
  { id: "all", label: "All events", types: [] },
  { id: "crossings", label: "Line crossings", types: ["line_crossed"] },
  { id: "zones", label: "Zone activity", types: ["zone_entered", "zone_exited"] },
  { id: "reads", label: "Reads (QR, barcode, text)", types: ["read"] },
  {
    id: "uptime",
    label: "Camera uptime",
    types: ["tracking_started", "tracking_stopped", "tracking_error", "tracking_reconnecting", "tracking_resumed"],
  },
];
