import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Layout from "./layout";

describe("Auth v2 layout", () => {
  it("replaces the lower security copy with a generated brand visual", () => {
    render(
      <Layout>
        <form aria-label="Sign in form" />
      </Layout>,
    );

    expect(screen.getByRole("img", { name: "DARKNETRA secure intelligence workspace visual" })).toHaveAttribute(
      "src",
      expect.stringContaining("/images/darknetra-auth-visual.png"),
    );
    expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
    expect(screen.queryByText("Auditable sessions")).not.toBeInTheDocument();
  });
});
