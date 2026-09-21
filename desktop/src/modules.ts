import type { AIModule } from "./api/types";

/** Display order for the module checkboxes; ids match the backend (app/modules.py). */
export const AI_MODULES: { id: AIModule; label: string }[] = [
  { id: "people", label: "People" },
  { id: "vehicles", label: "Vehicles" },
  { id: "ocr", label: "Text (OCR)" },
  { id: "qr", label: "QR codes" },
  { id: "barcode", label: "Barcodes" },
];

/** The modules whose output is a list of things read from the frame. */
export const READING_MODULES: AIModule[] = ["ocr", "qr", "barcode"];

export const READ_KIND_LABELS: Record<AIModule, string> = {
  people: "People",
  vehicles: "Vehicle",
  ocr: "Text",
  qr: "QR",
  barcode: "Barcode",
};
