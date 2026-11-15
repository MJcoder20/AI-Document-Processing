
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiRequest,
  clearAccessToken,
  getAccessToken,
  setAccessToken,
  SESSION_EXPIRED_EVENT,
} from "./apiClient";

describe("apiClient", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stores, retrieves, and clears the access token", () => {
    expect(getAccessToken()).toBeNull();

    setAccessToken("test-token");
    expect(getAccessToken()).toBe("test-token");

    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });

  it("sends requests with the configured API base URL", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiRequest<{ success: boolean }>("/documents/");

    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/documents\/$/),
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
    expect(result).toEqual({ success: true });
  });

  it("adds the bearer token to authenticated requests", async () => {
    setAccessToken("my-access-token");

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await apiRequest("/documents/");

    const requestOptions = vi.mocked(fetch).mock.calls[0][1];
    const headers = new Headers(requestOptions?.headers);

    expect(headers.get("Authorization")).toBe(
      "Bearer my-access-token",
    );
  });

  it("does not add authorization when no token exists", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await apiRequest("/auth/login");

    const requestOptions = vi.mocked(fetch).mock.calls[0][1];
    const headers = new Headers(requestOptions?.headers);

    expect(headers.has("Authorization")).toBe(false);
  });

  it("returns undefined for a 204 response", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    const result = await apiRequest<void>("/documents/123");

    expect(result).toBeUndefined();
  });

  it("throws the API error detail when a request fails", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Document not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiRequest("/documents/unknown")).rejects.toThrow(
      "Document not found",
    );
  });

  it("uses the status code when the error response has no detail", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("Invalid response", { status: 500 }),
    );

    await expect(apiRequest("/documents/")).rejects.toThrow(
      "Request failed with status 500",
    );
  });

  it("clears the token and dispatches session expiry on authenticated 401", async () => {
    setAccessToken("expired-token");

    const eventListener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, eventListener);

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiRequest("/auth/me")).rejects.toThrow("Unauthorized");

    expect(getAccessToken()).toBeNull();
    expect(eventListener).toHaveBeenCalledOnce();

    window.removeEventListener(SESSION_EXPIRED_EVENT, eventListener);
  });

  it("does not clear the token for a login 401 response", async () => {
    setAccessToken("existing-token");

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid credentials" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiRequest("/auth/login")).rejects.toThrow(
      "Invalid credentials",
    );

    expect(getAccessToken()).toBe("existing-token");
  });
});
