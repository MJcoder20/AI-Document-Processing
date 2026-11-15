
import {
  act,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import {
  getAccessToken,
  setAccessToken,
  SESSION_EXPIRED_EVENT,
} from "../services/apiClient";
import {
  getCurrentUser,
  loginUser,
  registerUser,
} from "../services/api";

vi.mock("../services/api", () => ({
  getCurrentUser: vi.fn(),
  loginUser: vi.fn(),
  registerUser: vi.fn(),
}));

function AuthConsumer() {
  const { user, loading, login, register, logout } = useAuth();

  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user?.email ?? "No user"}</span>

      <button
        onClick={() =>
          void login("test@example.com", "password123").catch(() => undefined)
        }
      >
        Login
      </button>

      <button
        onClick={() =>
          void register("test@example.com", "password123").catch(() => undefined)
        }
      >
        Register
      </button>

      <button onClick={logout}>Logout</button>
    </div>
  );
}

const mockUser = {
  id: "user-123",
  email: "test@example.com",
  role: "user",
  is_active: true,
  created_at: "2026-11-15T00:00:00Z",
};

function renderAuthProvider() {
  return render(
    <AuthProvider>
      <AuthConsumer />
    </AuthProvider>,
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("starts without a session when no token exists", async () => {
    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    expect(screen.getByTestId("user")).toHaveTextContent("No user");
    expect(getCurrentUser).not.toHaveBeenCalled();
  });

  it("restores an existing session", async () => {
    setAccessToken("existing-token");
    vi.mocked(getCurrentUser).mockResolvedValue(mockUser);

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent(
        "test@example.com",
      );
    });

    expect(getCurrentUser).toHaveBeenCalledOnce();
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
  });

  it("clears an invalid token during session restoration", async () => {
    setAccessToken("invalid-token");
    vi.mocked(getCurrentUser).mockRejectedValue(
      new Error("Invalid token"),
    );

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    expect(getAccessToken()).toBeNull();
    expect(screen.getByTestId("user")).toHaveTextContent("No user");
  });

  it("logs in and stores the access token", async () => {
    vi.mocked(loginUser).mockResolvedValue({
      access_token: "new-access-token",
      token_type: "bearer",
    });
    vi.mocked(getCurrentUser).mockResolvedValue(mockUser);

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    await act(async () => {
      screen.getByRole("button", { name: "Login" }).click();
    });

    expect(loginUser).toHaveBeenCalledWith({
      email: "test@example.com",
      password: "password123",
    });
    expect(getAccessToken()).toBe("new-access-token");
    expect(screen.getByTestId("user")).toHaveTextContent(
      "test@example.com",
    );
  });

  it("clears the token when fetching the user after login fails", async () => {
    vi.mocked(loginUser).mockResolvedValue({
      access_token: "temporary-token",
      token_type: "bearer",
    });
    vi.mocked(getCurrentUser).mockRejectedValue(
      new Error("Unable to fetch user"),
    );

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    await act(async () => {
      screen.getByRole("button", { name: "Login" }).click();
    });

    await waitFor(() => {
      expect(getAccessToken()).toBeNull();
    });

    expect(screen.getByTestId("user")).toHaveTextContent("No user");
  });

  it("registers a user and then logs in", async () => {
    vi.mocked(registerUser).mockResolvedValue(mockUser);
    vi.mocked(loginUser).mockResolvedValue({
      access_token: "registered-user-token",
      token_type: "bearer",
    });
    vi.mocked(getCurrentUser).mockResolvedValue(mockUser);

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    await act(async () => {
      screen.getByRole("button", { name: "Register" }).click();
    });

    expect(registerUser).toHaveBeenCalledWith({
      email: "test@example.com",
      password: "password123",
    });
    expect(loginUser).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBe("registered-user-token");
    expect(screen.getByTestId("user")).toHaveTextContent(
      "test@example.com",
    );
  });

  it("logs out and removes the access token", async () => {
    setAccessToken("existing-token");
    vi.mocked(getCurrentUser).mockResolvedValue(mockUser);

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent(
        "test@example.com",
      );
    });

    act(() => {
      screen.getByRole("button", { name: "Logout" }).click();
    });

    expect(getAccessToken()).toBeNull();
    expect(screen.getByTestId("user")).toHaveTextContent("No user");
  });

  it("clears the session when the session-expired event is dispatched", async () => {
    setAccessToken("existing-token");
    vi.mocked(getCurrentUser).mockResolvedValue(mockUser);

    renderAuthProvider();

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent(
        "test@example.com",
      );
    });

    act(() => {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });

    expect(getAccessToken()).toBeNull();
    expect(screen.getByTestId("user")).toHaveTextContent("No user");
  });
});
