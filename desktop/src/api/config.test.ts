import { afterEach, describe, expect, it, vi } from "vitest";
import { getApiBaseUrl, getDefaultApiBaseUrl, isValidBaseUrl, setApiBaseUrlOverride } from "./config";

describe("getApiBaseUrl", () => {
  afterEach(() => {
    setApiBaseUrlOverride(null);
  });

  it("falls back to the default when nothing is set", () => {
    expect(getApiBaseUrl()).toBe(getDefaultApiBaseUrl());
  });

  it("prefers a saved override over the default", () => {
    setApiBaseUrlOverride("http://example.test:9000");
    expect(getApiBaseUrl()).toBe("http://example.test:9000");
  });

  it("clearing the override falls back to the default again", () => {
    setApiBaseUrlOverride("http://example.test:9000");
    setApiBaseUrlOverride(null);
    expect(getApiBaseUrl()).toBe(getDefaultApiBaseUrl());
  });

  it("does not throw when localStorage.getItem throws (e.g. blocked storage)", () => {
    const spy = vi.spyOn(window.localStorage.__proto__, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => getApiBaseUrl()).not.toThrow();
    expect(getApiBaseUrl()).toBe(getDefaultApiBaseUrl());
    spy.mockRestore();
  });

  it("does not throw when localStorage.setItem throws", () => {
    const spy = vi.spyOn(window.localStorage.__proto__, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => setApiBaseUrlOverride("http://x")).not.toThrow();
    spy.mockRestore();
  });
});

describe("isValidBaseUrl", () => {
  it.each(["http://127.0.0.1:8000", "https://api.vero.ai"])("accepts %s", (value) => {
    expect(isValidBaseUrl(value)).toBe(true);
  });

  it.each(["not a url", "ftp://example.com", ""])("rejects %s", (value) => {
    expect(isValidBaseUrl(value)).toBe(false);
  });
});
