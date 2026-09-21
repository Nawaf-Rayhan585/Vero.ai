import { useMemo, useState, type ReactNode } from "react";
import { useCameras } from "../hooks/useCameras";
import { useAnalyticsSummary, useAnalyticsTimeseries, useHeatmapInfo } from "../hooks/useAnalytics";
import { useHeatmapImage } from "../hooks/useHeatmapImage";
import { BarChart, type BarBucket, type BarSeries } from "../components/charts/BarChart";
import { StatTile, StatTiles } from "../components/StatTile";
import { Card, EmptyState, ErrorNotice, Spinner } from "../components/ui";
import { formatBucketFull, formatBucketLabel, formatDuration, formatNumber } from "../lib/format";
import { ANALYTICS_PRESETS, analyticsRange, browserTimeZone, type AnalyticsPreset } from "../lib/ranges";
import type { TimeseriesPoint } from "../api/types";
import "./EventsAnalytics.css";

type MetricId = "people" | "vehicles" | "zones" | "reads";

interface Metric {
  label: string;
  series: { key: string; label: string; colorSlot: 1 | 2; pick: (p: TimeseriesPoint) => number }[];
}

// Series colours follow the series (in = slot 1, out = slot 2), never their rank or the metric.
const METRICS: Record<MetricId, Metric> = {
  people: {
    label: "People",
    series: [
      { key: "people_in", label: "In", colorSlot: 1, pick: (p) => p.people_in },
      { key: "people_out", label: "Out", colorSlot: 2, pick: (p) => p.people_out },
    ],
  },
  vehicles: {
    label: "Vehicles",
    series: [
      { key: "vehicle_in", label: "In", colorSlot: 1, pick: (p) => p.vehicle_in },
      { key: "vehicle_out", label: "Out", colorSlot: 2, pick: (p) => p.vehicle_out },
    ],
  },
  zones: {
    label: "Zone visits",
    series: [
      { key: "zone_entered", label: "Entered", colorSlot: 1, pick: (p) => p.zone_entered },
      { key: "zone_exited", label: "Left", colorSlot: 2, pick: (p) => p.zone_exited },
    ],
  },
  reads: {
    label: "Reads",
    series: [{ key: "reads", label: "Reads", colorSlot: 1, pick: (p) => p.reads }],
  },
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="analytics-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function HeatmapPanel({
  cameraId,
  since,
  until,
}: {
  cameraId: string;
  since: string;
  until: string;
}) {
  const query = useMemo(() => (cameraId ? { camera_id: cameraId, since, until } : null), [cameraId, since, until]);
  const info = useHeatmapInfo(query);
  const available = info.data?.available === true;
  const heat = useHeatmapImage(available ? query : null);

  if (!cameraId) {
    return <p className="analytics-note">Choose a camera above to see where people stood.</p>;
  }
  if (info.isLoading) return <Spinner label="Loading heatmap" />;
  if (info.isError) return <ErrorNotice message={info.error.message} />;
  if (!available) {
    return (
      <EmptyState title="No heatmap recorded for this camera in this period">
        Heat is saved while people are being tracked. Tick People on the AI Modules page and start tracking to build one.
      </EmptyState>
    );
  }
  if (heat.error) return <ErrorNotice message={heat.error.message} />;
  if (heat.isLoading || !heat.image) return <Spinner label="Drawing heatmap" />;

  return (
    <>
      <img className="heatmap-image" src={heat.image.url} alt="Heatmap of where people stood in this period" />
      <p className="heatmap-caption">
        {formatNumber(info.data?.samples ?? 0)} position samples.{" "}
        {heat.image.background === "snapshot"
          ? "Drawn over a current snapshot from the camera."
          : "The camera did not answer, so the heat is drawn on a plain background."}{" "}
        Heat is saved hourly, so the edges of the period are accurate to the hour.
        {info.data && info.data.ignored_samples > 0
          ? ` ${formatNumber(info.data.ignored_samples)} samples from a different camera resolution are not shown.`
          : ""}
      </p>
    </>
  );
}

export function AnalyticsPage() {
  const { data: cameras } = useCameras();
  const [cameraId, setCameraId] = useState("");
  const [preset, setPreset] = useState<AnalyticsPreset>("today");
  const [metricId, setMetricId] = useState<MetricId>("people");

  const tz = useMemo(() => browserTimeZone(), []);
  const range = useMemo(() => analyticsRange(preset), [preset]);
  const rangeQuery = useMemo(
    () => ({ since: range.since, until: range.until, camera_id: cameraId || undefined }),
    [range, cameraId],
  );

  const summary = useAnalyticsSummary(rangeQuery);
  const timeseries = useAnalyticsTimeseries(useMemo(() => ({ ...rangeQuery, bucket: range.bucket, tz }), [rangeQuery, range, tz]));

  const metric = METRICS[metricId];
  const points = timeseries.data?.points ?? [];
  const severalCameras = cameraId === "" && (cameras?.length ?? 0) > 1;

  const buckets: BarBucket[] = points.map((p) => ({
    label: formatBucketLabel(p.start, range.bucket, tz),
    fullLabel: formatBucketFull(p.start, range.bucket, tz),
    notRunning: p.tracked_seconds === 0,
    note:
      p.tracked_seconds === 0
        ? "Not running"
        : `Tracked ${formatDuration(p.tracked_seconds)}${severalCameras ? " (camera time, summed)" : ""}`,
  }));
  const series: BarSeries[] = metric.series.map((s) => ({
    key: s.key,
    label: s.label,
    colorSlot: s.colorSlot,
    values: points.map(s.pick),
  }));

  const data = summary.data;
  const zoneVisits = data?.zones.reduce((sum, zone) => sum + zone.entered, 0) ?? 0;
  const totalReads = data ? data.reads.qr + data.reads.barcode + data.reads.ocr : 0;
  // Not while the numbers are still the previous slice's: that would claim things about a slice we have not loaded.
  const nothingTracked = data !== undefined && !summary.isPlaceholderData && data.tracked_seconds === 0;

  return (
    <Card title="Analytics">
      <div className="filter-row">
        <label>
          Camera
          <select value={cameraId} onChange={(e) => setCameraId(e.currentTarget.value)}>
            <option value="">All cameras</option>
            {cameras?.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Period
          <select value={preset} onChange={(e) => setPreset(e.currentTarget.value as AnalyticsPreset)}>
            {ANALYTICS_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <span className="filter-row__note">Times shown in {tz}</span>
      </div>

      {summary.isError && <ErrorNotice message={summary.error.message} />}

      {data && (
        <StatTiles stale={summary.isPlaceholderData}>
          <StatTile label="People in" value={formatNumber(data.people_in)} />
          <StatTile label="People out" value={formatNumber(data.people_out)} />
          <StatTile label="Vehicles in" value={formatNumber(data.vehicle_in)} />
          <StatTile label="Vehicles out" value={formatNumber(data.vehicle_out)} />
          <StatTile label="Zone visits" value={formatNumber(zoneVisits)} />
          <StatTile label="Reads" value={formatNumber(totalReads)} hint="QR, barcode and text" />
          <StatTile label="Tracked" value={formatDuration(data.tracked_seconds)} hint="camera time in this period" />
        </StatTiles>
      )}

      {nothingTracked && (
        <p className="analytics-note">
          Nothing was tracked in this period, so there is nothing to count. Start tracking on a camera under AI Modules.
        </p>
      )}

      <Section title="Trend">
        <div className="filter-row">
          <label>
            Measure
            <select value={metricId} onChange={(e) => setMetricId(e.currentTarget.value as MetricId)}>
              {(Object.keys(METRICS) as MetricId[]).map((id) => (
                <option key={id} value={id}>
                  {METRICS[id].label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {timeseries.isError && <ErrorNotice message={timeseries.error.message} />}
        {timeseries.isLoading && <Spinner label="Loading chart" />}
        {timeseries.data && (
          <BarChart
            title={`${metric.label} per ${range.bucket}`}
            buckets={buckets}
            series={series}
            stale={timeseries.isPlaceholderData}
          />
        )}
      </Section>

      {data && (data.lines.length > 0 || data.zones.length > 0) && (
        <div className={`analytics-tables${summary.isPlaceholderData ? " analytics-tables--stale" : ""}`}>
          {data.lines.length > 0 && (
            <table className="breakdown-table">
              <caption>By line</caption>
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">People in</th>
                  <th scope="col">People out</th>
                  <th scope="col">Vehicles in</th>
                  <th scope="col">Vehicles out</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((line) => (
                  <tr key={`${line.line_id}-${line.name}`}>
                    <th scope="row">{line.name ?? "(deleted line)"}</th>
                    <td>{formatNumber(line.people_in)}</td>
                    <td>{formatNumber(line.people_out)}</td>
                    <td>{formatNumber(line.vehicle_in)}</td>
                    <td>{formatNumber(line.vehicle_out)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.zones.length > 0 && (
            <table className="breakdown-table">
              <caption>By zone</caption>
              <thead>
                <tr>
                  <th scope="col">Zone</th>
                  <th scope="col">Entered</th>
                  <th scope="col">Left</th>
                </tr>
              </thead>
              <tbody>
                {data.zones.map((zone) => (
                  <tr key={`${zone.zone_id}-${zone.name}`}>
                    <th scope="row">{zone.name ?? "(deleted zone)"}</th>
                    <td>{formatNumber(zone.entered)}</td>
                    <td>{formatNumber(zone.exited)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <Section title="Heatmap">
        <HeatmapPanel cameraId={cameraId} since={range.since} until={range.until} />
      </Section>
    </Card>
  );
}
