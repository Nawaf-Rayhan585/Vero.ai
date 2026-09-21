import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BarChart, barPath, niceScale, type BarBucket, type BarSeries } from "./BarChart";

const IN: BarSeries = { key: "in", label: "In", colorSlot: 1, values: [3, 0, 12] };
const OUT: BarSeries = { key: "out", label: "Out", colorSlot: 2, values: [1, 0, 4] };

function makeBuckets(overrides: Partial<BarBucket>[] = []): BarBucket[] {
  return [
    { label: "9 AM", fullLabel: "Tue, Mar 10, 9 AM", note: "Tracked 1 h" },
    { label: "10 AM", fullLabel: "Tue, Mar 10, 10 AM", note: "Not running", notRunning: true },
    { label: "11 AM", fullLabel: "Tue, Mar 10, 11 AM", note: "Tracked 30 min" },
  ].map((bucket, i) => ({ ...bucket, ...overrides[i] }));
}

function bars(container: HTMLElement): SVGPathElement[] {
  return Array.from(container.querySelectorAll("svg path"));
}

describe("niceScale", () => {
  it("gives whole-number ticks that reach the data", () => {
    expect(niceScale(7)).toEqual({ max: 8, ticks: [0, 2, 4, 6, 8] });
    expect(niceScale(23)).toEqual({ max: 30, ticks: [0, 10, 20, 30] }); // 5.75 per tick rounds up to a clean 10
    expect(niceScale(1000)).toEqual({ max: 1000, ticks: [0, 500, 1000] });
  });

  it("never uses fractional steps for counts", () => {
    expect(niceScale(1)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceScale(2).ticks.every(Number.isInteger)).toBe(true);
  });

  it("still draws a sensible axis when everything is zero", () => {
    expect(niceScale(0)).toEqual({ max: 4, ticks: [0, 1, 2, 3, 4] });
    expect(niceScale(-3).max).toBe(4);
  });

  it("the top tick is never below the data", () => {
    for (const max of [1, 2, 3, 9, 10, 11, 99, 101, 4999]) {
      expect(niceScale(max).max).toBeGreaterThanOrEqual(max);
    }
  });
});

describe("barPath", () => {
  it("grows from a square baseline up to a rounded top", () => {
    const d = barPath(10, 20, 24, 100);

    expect(d.startsWith("M10,120")).toBe(true); // starts at the base, bottom-left, a hard corner
    expect(d).toContain("Q10,20"); // rounded top-left
    expect(d).toContain("Q34,20"); // rounded top-right
    expect(d.endsWith("Z")).toBe(true);
  });

  it("caps the corner radius so a tiny bar is not drawn inside out", () => {
    expect(barPath(0, 0, 24, 2)).toContain("V2"); // radius 2, not 4
    expect(barPath(0, 0, 3, 100)).toContain("H1.5"); // narrower than 2 radii: radius = half the width
  });
});

describe("BarChart", () => {
  it("draws a bar for every non-zero value, and none for zeros", () => {
    const { container } = render(<BarChart title="People per hour" buckets={makeBuckets()} series={[IN, OUT]} />);

    expect(bars(container)).toHaveLength(4); // in: 3 and 12; out: 1 and 4
  });

  it("colours each series by its slot, never by its rank", () => {
    const { container } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);

    const styles = bars(container).map((p) => p.getAttribute("style") ?? "");
    expect(styles.filter((s) => s.includes("--chart-series-1"))).toHaveLength(2);
    expect(styles.filter((s) => s.includes("--chart-series-2"))).toHaveLength(2);
  });

  it("caps a bar's width at 24px, however much room there is", () => {
    const { container } = render(
      <BarChart title="t" buckets={makeBuckets().slice(0, 1)} series={[{ ...IN, values: [10] }]} />,
    );

    const d = bars(container)[0].getAttribute("d") ?? "";
    const x0 = Number(d.match(/^M([\d.]+),/)![1]);
    const rightCorner = Number(d.match(/H([\d.]+)/)![1]) + 4; // the top edge stops one corner short
    expect(rightCorner - x0).toBeCloseTo(24, 5);
  });

  it("puts the taller value higher", () => {
    const { container } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN]} />);

    const tops = bars(container).map((p) => Number((p.getAttribute("d") ?? "").match(/Q[\d.]+,([\d.]+)/)![1]));
    expect(tops[1]).toBeLessThan(tops[0]); // 12 is higher up than 3
  });

  it("shows a legend for two series, and a hatched 'Not running' entry only when a bucket was not running", () => {
    const { rerender } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);
    expect(screen.getByText("In")).toBeInTheDocument();
    expect(screen.getByText("Out")).toBeInTheDocument();
    expect(screen.getByText("Not running")).toBeInTheDocument();

    rerender(<BarChart title="t" buckets={makeBuckets([{ notRunning: false }, { notRunning: false }])} series={[IN, OUT]} />);
    expect(screen.queryByText("Not running")).not.toBeInTheDocument();
  });

  it("a single series needs no legend box: the title already says what it is", () => {
    render(<BarChart title="Reads per hour" buckets={makeBuckets([{ notRunning: false }, { notRunning: false }])} series={[{ ...IN, label: "Reads" }]} />);

    expect(screen.queryByText("Reads")).not.toBeInTheDocument(); // not as a legend entry (it's in the group's label)
    expect(document.querySelector(".chart__legend-item")).toBeNull();
  });

  it("hatches the buckets where nothing was being tracked instead of drawing an empty bar", () => {
    const { container } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);

    const hatched = container.querySelectorAll('rect[fill^="url(#hatch"]');
    expect(hatched).toHaveLength(1);
    expect(container.querySelectorAll("pattern")).toHaveLength(1);
  });

  it("gives every bucket a focusable, labelled target that states its values and its status", () => {
    render(<BarChart title="People per hour" buckets={makeBuckets()} series={[IN, OUT]} />);

    const targets = screen.getAllByRole("img");
    expect(targets).toHaveLength(3);
    expect(targets[0]).toHaveAttribute("aria-label", "Tue, Mar 10, 9 AM: 3 in, 1 out. Tracked 1 h");
    expect(targets[1]).toHaveAttribute("aria-label", expect.stringContaining("Not running"));
    expect(targets[2]).toHaveAttribute("tabindex", "0");
  });

  it("names the whole chart for assistive technology", () => {
    render(<BarChart title="People per hour" buckets={makeBuckets()} series={[IN, OUT]} />);

    expect(screen.getByRole("group", { name: "People per hour" })).toBeInTheDocument();
  });

  it("shows a tooltip on hover, values first, and hides it again", async () => {
    const user = userEvent.setup();
    render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    await user.hover(screen.getAllByRole("img")[2]);

    const tooltip = screen.getByRole("status");
    expect(within(tooltip).getByText("Tue, Mar 10, 11 AM")).toBeInTheDocument();
    expect(within(tooltip).getByText("12")).toBeInTheDocument();
    expect(within(tooltip).getByText("4")).toBeInTheDocument();
    expect(within(tooltip).getByText("Tracked 30 min")).toBeInTheDocument();

    await user.unhover(screen.getAllByRole("img")[2]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows the same tooltip on keyboard focus, so nothing depends on a mouse", () => {
    render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);

    fireEvent.focus(screen.getAllByRole("img")[0]);
    expect(within(screen.getByRole("status")).getByText("Tue, Mar 10, 9 AM")).toBeInTheDocument();

    fireEvent.blur(screen.getAllByRole("img")[0]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("the tooltip says a bucket was not running, rather than showing zeros as if it had been", async () => {
    const user = userEvent.setup();
    render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);

    await user.hover(screen.getAllByRole("img")[1]);

    expect(within(screen.getByRole("status")).getByText("Not running")).toBeInTheDocument();
  });

  it("offers a table of the same numbers, and can hide it again", async () => {
    const user = userEvent.setup();
    render(<BarChart title="People per hour" buckets={makeBuckets()} series={[IN, OUT]} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show table" }));

    const table = screen.getByRole("table");
    expect(within(table).getByText("People per hour")).toBeInTheDocument(); // caption
    expect(within(table).getAllByRole("row")).toHaveLength(4); // header + 3 buckets
    const lastRow = within(table).getAllByRole("row")[3];
    expect(within(lastRow).getByText("Tue, Mar 10, 11 AM")).toBeInTheDocument();
    expect(within(lastRow).getByText("12")).toBeInTheDocument();
    expect(within(lastRow).getByText("Tracked 30 min")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide table" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Hide table" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("thins the x-axis labels when there are many buckets, so they never collide", () => {
    const many = Array.from({ length: 24 }, (_, i) => ({ label: `h${i}`, fullLabel: `hour ${i}` }));
    const { container } = render(<BarChart title="t" buckets={many} series={[{ ...IN, values: many.map(() => 1) }]} />);

    const labels = Array.from(container.querySelectorAll("text.chart__tick")).map((t) => t.textContent);
    expect(labels).toContain("h0");
    expect(labels).toContain("h3");
    expect(labels).not.toContain("h1"); // every third label
    expect(labels.filter((l) => l?.startsWith("h")).length).toBeLessThanOrEqual(8);
  });

  it("labels every bucket when there are few", () => {
    const { container } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN]} />);

    const labels = Array.from(container.querySelectorAll("text.chart__tick")).map((t) => t.textContent);
    expect(labels).toEqual(expect.arrayContaining(["9 AM", "10 AM", "11 AM"]));
  });

  it("draws the y axis with whole-number ticks and a solid baseline", () => {
    const { container } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);

    const ticks = Array.from(container.querySelectorAll("text.chart__tick")).map((t) => t.textContent);
    expect(ticks).toEqual(expect.arrayContaining(["0", "5", "10", "15"]));
    expect(container.querySelectorAll("line.chart__axis")).toHaveLength(1);
    expect(container.querySelectorAll("line.chart__grid").length).toBeGreaterThan(0);
  });

  it("dims the chart, rather than replacing it, while a new slice loads", () => {
    const { container, rerender } = render(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} />);
    expect(container.querySelector(".chart--stale")).toBeNull();

    rerender(<BarChart title="t" buckets={makeBuckets()} series={[IN, OUT]} stale />);

    expect(container.querySelector(".chart--stale")).not.toBeNull();
    expect(bars(container).length).toBeGreaterThan(0); // the previous render is still there
  });

  it("says so when there is no data at all", () => {
    render(<BarChart title="t" buckets={[]} series={[IN]} />);

    expect(screen.getByText("No data for this range.")).toBeInTheDocument();
  });

  it("copes with all-zero data: no bars, an axis anyway", () => {
    const zeros: BarSeries = { ...IN, values: [0, 0, 0] };
    const { container } = render(<BarChart title="t" buckets={makeBuckets([{ notRunning: false }, { notRunning: false }])} series={[zeros]} />);

    expect(bars(container)).toHaveLength(0);
    expect(container.querySelectorAll("text.chart__tick").length).toBeGreaterThan(3);
  });

  it("shows series and bucket names as plain text, never as markup", async () => {
    const user = userEvent.setup();
    const hostile: BarBucket[] = [{ label: "x", fullLabel: "<img src=x onerror=alert(1)>" }];
    const { container } = render(<BarChart title="t" buckets={hostile} series={[{ ...IN, label: "<b>bold</b>", values: [1] }]} />);

    await user.hover(screen.getAllByRole("img")[0]);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });
});
