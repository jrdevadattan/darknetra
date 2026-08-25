import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CaseShell } from "./case-shell";
import { CaseOverview as CaseOverviewForTest } from "./case-overview";
import { CasesLiveView } from "./cases-live-view";

vi.mock("next/navigation", () => ({
  usePathname: () => "/cases/4d61f3aa-b46e-4ed2-b516-e91ec5930abc",
}));

const fetchMock = vi.fn();

const API_CASE = {
  id: "4d61f3aa-b46e-4ed2-b516-e91ec5930abc",
  case_code: "CHD-2026-001",
  title: "Synthetic narcotics case",
  status: "OPEN",
  sensitivity: "STANDARD",
  owner_user_id: "2b18f363-8fc0-44aa-8312-7f4792e663af",
  source_authority_summary: "Authorized synthetic fixture for investigator training",
  created_at: "2026-08-17T09:30:00Z",
  updated_at: "2026-08-17T10:45:00Z",
  closed_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("CasesLiveView", () => {
  it("creates a case and refreshes the visible case inventory", async () => {
    const user = userEvent.setup();
    const createdCase = {
      ...API_CASE,
      id: "22175f61-f785-4756-94f0-af398e415314",
      case_code: "DARKNETRA-001",
      title: "First dashboard-created case",
      updated_at: "2026-08-18T10:45:00Z",
    };

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [], limit: 25, offset: 0, has_more: false }))
      .mockResolvedValueOnce(jsonResponse(createdCase, 201))
      .mockResolvedValueOnce(jsonResponse({ items: [createdCase], limit: 25, offset: 0, has_more: false }));

    renderWithQuery(<CasesLiveView />);

    await screen.findByText("Operational case inventory");
    await user.click(screen.getByRole("button", { name: "New case" }));
    await user.type(screen.getByLabelText("Case code"), "DARKNETRA-001");
    await user.type(screen.getByLabelText("Title"), "First dashboard-created case");
    await user.selectOptions(screen.getAllByLabelText("Sensitivity")[0], "STANDARD");
    await user.type(screen.getByLabelText("Source authority"), "Authorized synthetic training source");
    await user.click(screen.getByRole("button", { name: "Create case" }));

    expect(await screen.findByRole("link", { name: "First dashboard-created case" })).toHaveAttribute(
      "href",
      `/cases/${createdCase.id}`,
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/cases",
      expect.objectContaining({
        body: JSON.stringify({
          case_code: "DARKNETRA-001",
          title: "First dashboard-created case",
          sensitivity: "STANDARD",
          source_authority_summary: "Authorized synthetic training source",
        }),
        method: "POST",
      }),
    );
  });

  it("shows a newly created case immediately when the refetch is still in flight", async () => {
    const user = userEvent.setup();
    const createdCase = {
      ...API_CASE,
      id: "b80d5b59-1c6d-4f59-ae7c-9e9aa282f4bf",
      case_code: "DARKNETRA-2026-014",
      title: "Marketplace wallet attribution review",
      source_authority_summary: "Authorized case material received under court order 26-481",
      updated_at: "2026-08-25T14:20:00Z",
    };

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [], limit: 100, offset: 0, has_more: false }))
      .mockResolvedValueOnce(jsonResponse(createdCase, 201))
      .mockImplementationOnce(() => new Promise<Response>(() => undefined));

    renderWithQuery(<CasesLiveView />);

    await screen.findByText("Operational case inventory");
    await user.click(screen.getByRole("button", { name: "New case" }));
    await user.type(screen.getByLabelText("Case code"), createdCase.case_code);
    await user.type(screen.getByLabelText("Title"), createdCase.title);
    await user.selectOptions(screen.getAllByLabelText("Sensitivity")[0], "STANDARD");
    await user.type(screen.getByLabelText("Source authority"), createdCase.source_authority_summary);
    await user.click(screen.getByRole("button", { name: "Create case" }));

    expect(await screen.findByRole("link", { name: createdCase.title })).toHaveAttribute(
      "href",
      `/cases/${createdCase.id}`,
    );
    expect(screen.getByText(createdCase.case_code)).toBeInTheDocument();
    expect(screen.getByText("Collection")).toBeInTheDocument();
  });

  it("renders live API cases through the retained table interface", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [API_CASE], limit: 25, offset: 0, has_more: false }));

    renderWithQuery(<CasesLiveView />);

    expect(screen.getByTestId("async-state-loading")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: API_CASE.title })).toHaveAttribute("href", `/cases/${API_CASE.id}`);
    expect(screen.queryByText(/fixture inventory/i)).not.toBeInTheDocument();
  });

  it("shows an operational case inventory when the visible case list is empty", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [], limit: 25, offset: 0, has_more: false }));

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText("Operational case inventory")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marketplace alias and wallet correlation" })).toHaveAttribute(
      "href",
      "/cases/snapshot-marketplace-correlation",
    );
    expect(screen.getByText("DN-INT-7842")).toBeInTheDocument();
    expect(screen.queryByText("No visible cases")).not.toBeInTheDocument();
  });

  it("shows access denied instead of fixture fallback on authorization failure", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "permission denied" }, 403));

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText("Case access denied")).toBeInTheDocument();
    expect(screen.queryByText("Alias correlation training case")).not.toBeInTheDocument();
  });

  it("shows an offline state when the API cannot be reached", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("network unavailable"));

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText("Case service offline")).toBeInTheDocument();
  });
});

describe("CaseShell", () => {
  it("renders a live case header and its child route when the case is visible", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(API_CASE));

    renderWithQuery(
      <CaseShell caseId={API_CASE.id}>
        <p>Child route content</p>
      </CaseShell>,
    );

    expect(await screen.findByRole("heading", { name: API_CASE.title })).toBeInTheDocument();
    expect(screen.getByText("Child route content")).toBeInTheDocument();
  });

  it("explains case processing and evidence collection without showing narration content", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(API_CASE)).mockResolvedValueOnce(jsonResponse(API_CASE));

    renderWithQuery(
      <CaseShell caseId={API_CASE.id}>
        <CaseOverviewForTest caseId={API_CASE.id} />
      </CaseShell>,
    );

    expect(await screen.findByText("Process flow")).toBeInTheDocument();
    expect(screen.getByText("Evidence collection")).toBeInTheDocument();
    expect(screen.getByText("Evidence ledger")).toBeInTheDocument();
    expect(screen.getByText("Correlation graph")).toBeInTheDocument();
    expect(screen.getByText("Entity extraction")).toBeInTheDocument();
    expect(screen.getByText("Alert queue")).toBeInTheDocument();
    expect(screen.getByText("Report package")).toBeInTheDocument();
    expect(screen.getByText("34,982 observations indexed")).toBeInTheDocument();
    expect(screen.getByText("12 linked entities")).toBeInTheDocument();
    expect(screen.getByText("9 evidence artifacts")).toBeInTheDocument();
    expect(screen.queryByText("2–5 minute selection script")).not.toBeInTheDocument();
    expect(screen.queryByText("Video walkthrough script")).not.toBeInTheDocument();
    expect(screen.queryByText(/This is DARKNETRA: an evidence-first intelligence workspace/)).not.toBeInTheDocument();
    expect(screen.getAllByText(API_CASE.case_code).length).toBeGreaterThan(0);
    expect(screen.getByText(API_CASE.source_authority_summary)).toBeInTheDocument();
  });

  it("masks unknown and inaccessible cases without rendering child fixture content", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "resource not found" }, 404));

    renderWithQuery(
      <CaseShell caseId="b4ab65f9-f6bc-46f0-94df-792892b90b83">
        <p>Should never render</p>
      </CaseShell>,
    );

    expect(await screen.findByText("Case unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Should never render")).not.toBeInTheDocument();
  });
});
