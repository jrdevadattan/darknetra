import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseOperationalSurface, GlobalOperationalSurface } from "./operational-surfaces";

describe("operational investigation surfaces", () => {
  it("renders intelligence trends with charts and processing flow instead of placeholder copy", () => {
    render(<GlobalOperationalSurface surface="trends" />);

    expect(screen.getByText("Emerging Trends")).toBeInTheDocument();
    expect(screen.getByText("Activity signal timeline")).toBeInTheDocument();
    expect(screen.getByText("Term velocity")).toBeInTheDocument();
    expect(screen.getByText("Investigation flow")).toBeInTheDocument();
    expect(screen.queryByText(/will appear/i)).not.toBeInTheDocument();
  });

  it("renders audit as an event timeline with integrity checkpoints", () => {
    render(<GlobalOperationalSurface surface="audit" />);

    expect(screen.getByText("Audit")).toBeInTheDocument();
    expect(screen.getByText("Audit trail timeline")).toBeInTheDocument();
    expect(screen.getByText("Session controls")).toBeInTheDocument();
    expect(screen.getByText("Integrity checkpoints")).toBeInTheDocument();
    expect(screen.queryByText(/will appear/i)).not.toBeInTheDocument();
  });

  it("renders case evidence, graph, and report tabs as working operational views", () => {
    const { rerender } = render(<CaseOperationalSurface surface="evidence" />);
    expect(screen.getByText("Evidence vault")).toBeInTheDocument();
    expect(screen.getByText("Custody chain")).toBeInTheDocument();
    expect(screen.getByText("Collection pipeline")).toBeInTheDocument();

    rerender(<CaseOperationalSurface surface="graph" />);
    expect(screen.getByText("Correlation graph")).toBeInTheDocument();
    expect(screen.getByText("Entity relationship map")).toBeInTheDocument();

    rerender(<CaseOperationalSurface surface="reports" />);
    expect(screen.getByText("Report package")).toBeInTheDocument();
    expect(screen.getByText("Package readiness")).toBeInTheDocument();
    expect(screen.queryByText(/will appear/i)).not.toBeInTheDocument();
  });
});
