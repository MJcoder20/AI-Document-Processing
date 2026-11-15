
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuthScreen from "./AuthScreen";
import { useAuth } from "../context/AuthContext";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockLogin = vi.fn();
const mockRegister = vi.fn();

function renderAuthScreen() {
  return render(<AuthScreen />);
}

describe("AuthScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      login: mockLogin,
      register: mockRegister,
      logout: vi.fn(),
    });
  });

  it("renders the login screen by default", () => {
    renderAuthScreen();

    expect(
      screen.getByRole("heading", { name: "Welcome back" }),
    ).toBeInTheDocument();

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign In" }),
    ).toBeInTheDocument();

    expect(
      screen.queryByLabelText("Confirm password"),
    ).not.toBeInTheDocument();
  });

  it("switches to registration mode", () => {
    renderAuthScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );

    expect(
      screen.getByRole("heading", { name: "Create your account" }),
    ).toBeInTheDocument();

    expect(
      screen.getByLabelText("Confirm password"),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Create Account" }),
    ).toBeInTheDocument();
  });

  it("shows an error when registration passwords do not match", async () => {
    renderAuthScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );

    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "test@example.com" },
    });

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });

    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "different123" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Create Account" }),
    );

    expect(await screen.findByText("Passwords do not match."))
      .toBeInTheDocument();

    expect(mockRegister).not.toHaveBeenCalled();
  });

  it("calls login with the entered credentials", async () => {
    mockLogin.mockResolvedValue(undefined);

    renderAuthScreen();

    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "test@example.com" },
    });

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith(
        "test@example.com",
        "password123",
      );
    });
  });

  it("displays login errors", async () => {
    mockLogin.mockRejectedValue(new Error("Invalid credentials"));

    renderAuthScreen();

    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "test@example.com" },
    });

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrongpassword" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect(await screen.findByText("Invalid credentials"))
      .toBeInTheDocument();
  });

  it("calls register with matching credentials", async () => {
    mockRegister.mockResolvedValue(undefined);

    renderAuthScreen();

    fireEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );

    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "new@example.com" },
    });

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });

    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "password123" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Create Account" }),
    );

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith(
        "new@example.com",
        "password123",
      );
    });
  });

  it("clears password fields and errors when switching modes", async () => {
    mockLogin.mockRejectedValue(new Error("Invalid credentials"));

    renderAuthScreen();

    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "test@example.com" },
    });

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrongpassword" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect(await screen.findByText("Invalid credentials"))
      .toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );

    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm password")).toHaveValue("");
    expect(screen.queryByText("Invalid credentials"))
      .not.toBeInTheDocument();
  });
});
