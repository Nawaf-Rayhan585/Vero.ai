import { useMemo, useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useEvents } from "../hooks/useEvents";
import { Button, Card, EmptyState, ErrorNotice, Spinner, StatusBadge } from "../components/ui";
import { EVENT_FILTER_GROUPS, describeEvent } from "../lib/describeEvent";
import { formatEventTime } from "../lib/format";
import { EVENTS_PRESETS, eventsSince, type EventsPreset } from "../lib/ranges";
import "./EventsAnalytics.css";

export function EventsPage() {
  const { data: cameras } = useCameras();
  const [cameraId, setCameraId] = useState("");
  const [groupId, setGroupId] = useState("all");
  const [preset, setPreset] = useState<EventsPreset>("all");

  const group = EVENT_FILTER_GROUPS.find((g) => g.id === groupId) ?? EVENT_FILTER_GROUPS[0];
  const since = useMemo(() => eventsSince(preset), [preset]);
  const filters = useMemo(
    () => ({
      camera_id: cameraId || undefined,
      event_type: group.types.length > 0 ? group.types : undefined,
      since,
    }),
    [cameraId, group, since],
  );

  const events = useEvents(filters);
  const rows = events.data?.pages.flatMap((page) => page.events) ?? [];

  return (
    <Card title="Events">
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
          Type
          <select value={groupId} onChange={(e) => setGroupId(e.currentTarget.value)}>
            {EVENT_FILTER_GROUPS.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Period
          <select value={preset} onChange={(e) => setPreset(e.currentTarget.value as EventsPreset)}>
            {EVENTS_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <span className="filter-row__note">Newest first · updates automatically</span>
      </div>

      {events.isLoading && <Spinner label="Loading events" />}
      {events.isError && <ErrorNotice message={events.error.message} />}

      {!events.isLoading && !events.isError && rows.length === 0 && (
        <EmptyState title="No events yet">
          Events appear here as cameras run: people and vehicles crossing lines, zone activity, QR codes, barcodes and
          text that were read, and when tracking starts or stops. Start tracking on a camera under AI Modules.
        </EmptyState>
      )}

      {rows.length > 0 && (
        <ul className="event-list">
          {rows.map((event) => {
            const description = describeEvent(event);
            return (
              <li key={event.id} className="event-row">
                <span className="event-row__time">{formatEventTime(event.occurred_at)}</span>
                <span>{event.camera_name}</span>
                <span>
                  <StatusBadge label={description.title} tone={description.tone} />
                </span>
                <span className="event-row__detail">{description.detail}</span>
              </li>
            );
          })}
        </ul>
      )}

      {events.hasNextPage && (
        <Button onClick={() => events.fetchNextPage()} disabled={events.isFetchingNextPage}>
          {events.isFetchingNextPage ? "Loading..." : "Load more"}
        </Button>
      )}
    </Card>
  );
}
