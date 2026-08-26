import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourceRegistryLiveView } from "./source-registry-live-view";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("SourceRegistryLiveView", () => {
  it("renders the API integration catalog and evidence processing flow", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        items: [
          {
            slug: "robin",
            name: "Robin",
            repository_url: "https://github.com/apurvsinghgautam/robin",
            integration_mode: "IMPORT",
            pipeline_role: "Import investigation reports into evidence processing.",
            accepted_outputs: ["report", "markdown"],
          },
          {
            slug: "torbot",
            name: "TorBot",
            repository_url: "https://github.com/DedSecInside/TorBot",
            integration_mode: "IMPORT",
            pipeline_role: "Normalize bounded JSON link trees.",
            accepted_outputs: ["json-link-tree"],
          },
        ],
      }),
    );

    renderWithQuery(<SourceRegistryLiveView />);

    expect(await screen.findByRole("link", { name: "Robin" })).toHaveAttribute(
      "href",
      "https://github.com/apurvsinghgautam/robin",
    );
    expect(screen.getByRole("link", { name: "TorBot" })).toBeInTheDocument();
    expect(screen.getByText("Authorized intelligence flow")).toBeInTheDocument();
    expect(screen.getByText("Preserve and hash")).toBeInTheDocument();
    expect(screen.queryByText("Source readiness matrix")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/intelligence/integrations",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("shows an explicit unavailable state when the integration API cannot be reached", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("network unavailable"));

    renderWithQuery(<SourceRegistryLiveView />);

    expect(await screen.findByText("Integration service offline")).toBeInTheDocument();
  });

  it("submits a Robin package to the normalization API and displays its integrity result", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              slug: "robin",
              name: "Robin",
              repository_url: "https://github.com/apurvsinghgautam/robin",
              integration_mode: "IMPORT",
              pipeline_role: "Import investigation reports into evidence processing.",
              accepted_outputs: ["report", "markdown"],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          adapter: "robin",
          content_sha256: "a".repeat(64),
          observations: [
            {
              kind: "REPORT",
              value: "# Investigation",
              provenance: "Authorized Robin report",
              title: "Investigation",
              parent: null,
            },
          ],
        }),
      );

    renderWithQuery(<SourceRegistryLiveView />);
    await screen.findByRole("link", { name: "Robin" });
    fireEvent.change(screen.getByLabelText("Source name"), {
      target: { value: "Authorized Robin report" },
    });
    fireEvent.change(screen.getByLabelText("Intelligence package"), {
      target: { files: [new File(["# Investigation"], "report.md", { type: "text/markdown" })] },
    });
    const submit = screen.getByRole("button", { name: "Normalize package" });
    await waitFor(() => expect(submit).toBeEnabled());
    const form = submit.closest("form");
    expect(form).not.toBeNull();
    if (form) fireEvent.submit(form);

    expect(await screen.findByText("Package normalized")).toBeInTheDocument();
    expect(screen.getByText(/aaaaaaaaaaaa/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "http://localhost:8000/api/v1/intelligence/integrations/robin/normalize",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});
