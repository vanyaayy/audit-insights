import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Findings } from "../pages/Findings";
import { renderPage, mockApi } from "./render";
import { FINDINGS } from "./fixtures";

describe("Findings register", () => {
  it("filters by severity and opens a finding with its source evidence", async () => {
    mockApi({
      "/api/findings": FINDINGS,
      "/api/findings/fy2022_23-07": FINDINGS[1],
    });
    const user = userEvent.setup();
    renderPage(<Findings />, "/findings");

    expect(await screen.findByText(/Showing/)).toHaveTextContent("Showing 3 of 3 findings");

    await user.selectOptions(screen.getByLabelText("Severity"), "Medium");
    expect(screen.getByText(/Showing/)).toHaveTextContent("Showing 1 of 3 findings");
    expect(screen.getByRole("button", { name: /Remove Severity filter/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open finding fy2022_23-07" }));
    const drawer = await screen.findByRole("dialog", { name: "Finding detail" });
    expect(within(drawer).getByRole("heading", { name: "Accounts of leavers were not removed." })).toBeInTheDocument();
    expect(within(drawer).getByRole("img", { name: /quote highlighted/ })).toHaveAttribute(
      "src", "/api/findings/fy2022_23-07/evidence/0.png",
    );
  });

  it("flags findings whose quotes were not found and filters to them", async () => {
    mockApi({ "/api/findings": FINDINGS });
    const user = userEvent.setup();
    renderPage(<Findings />, "/findings");

    expect(await screen.findByText(/1 finding needs review/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show them" }));
    expect(screen.getByText(/Showing/)).toHaveTextContent("Showing 1 of 3 findings");
    expect(screen.getByText("System errors in subsidy computation.")).toBeInTheDocument();
  });
});
