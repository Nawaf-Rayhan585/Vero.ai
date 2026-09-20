import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { getApiBaseUrl, getDefaultApiBaseUrl, setApiBaseUrlOverride } from "../api/config";
import type { ModelType } from "../api/types";

const DEFAULT_MODEL_KEY = "vero.defaultModelType";
const DEFAULT_CONFIDENCE_KEY = "vero.defaultConfidenceThreshold";
const DEFAULT_MODEL: ModelType = "yolo";
const DEFAULT_CONFIDENCE = 0.25;

function readString(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function readNumber(key: string, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw === null ? NaN : Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function writeValue(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable — the setting just won't persist across restarts.
  }
}

interface SettingsContextValue {
  defaultModelType: ModelType;
  setDefaultModelType: (value: ModelType) => void;
  defaultConfidenceThreshold: number;
  setDefaultConfidenceThreshold: (value: number) => void;
  apiBaseUrl: string;
  setApiBaseUrl: (value: string | null) => void;
  defaultApiBaseUrl: string;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [defaultModelType, setModelState] = useState<ModelType>(() =>
    readString(DEFAULT_MODEL_KEY, DEFAULT_MODEL) as ModelType,
  );
  const [defaultConfidenceThreshold, setConfidenceState] = useState<number>(() =>
    readNumber(DEFAULT_CONFIDENCE_KEY, DEFAULT_CONFIDENCE),
  );
  const [apiBaseUrl, setApiBaseUrlState] = useState<string>(() => getApiBaseUrl());

  const value = useMemo<SettingsContextValue>(
    () => ({
      defaultModelType,
      setDefaultModelType: (next) => {
        setModelState(next);
        writeValue(DEFAULT_MODEL_KEY, next);
      },
      defaultConfidenceThreshold,
      setDefaultConfidenceThreshold: (next) => {
        setConfidenceState(next);
        writeValue(DEFAULT_CONFIDENCE_KEY, String(next));
      },
      apiBaseUrl,
      setApiBaseUrl: (next) => {
        setApiBaseUrlOverride(next);
        setApiBaseUrlState(next && next.trim() ? next.trim() : getDefaultApiBaseUrl());
      },
      defaultApiBaseUrl: getDefaultApiBaseUrl(),
    }),
    [defaultModelType, defaultConfidenceThreshold, apiBaseUrl],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within a SettingsProvider");
  return ctx;
}
