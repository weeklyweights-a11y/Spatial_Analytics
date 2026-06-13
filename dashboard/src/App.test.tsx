import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryProvider } from "./providers/QueryProvider";
import LoginPage from "./pages/Login";

describe("App", () => {
  it("renders login page", () => {
    render(
      <QueryProvider>
        <BrowserRouter>
          <LoginPage />
        </BrowserRouter>
      </QueryProvider>
    );
    expect(screen.getByText("SpatialScore")).toBeTruthy();
    expect(screen.getByPlaceholderText("Username")).toBeTruthy();
  });
});
