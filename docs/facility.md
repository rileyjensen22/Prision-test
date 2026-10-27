# The facility model (Phase 20)

## Shape

Site, hub, line, floor, cell, recreation room. In the target facility there are **5 hubs, 6 lines to a hub, 4 floors to a line and 16 cells to a floor (one hallway per floor)**, which is 1,920 cells. The housing unit is the line: a cell's `unit` and `line_code` are its line's code (`H2-L3`), which is also the unit the schedule, keep-separate checks and chess use. Each line has four day rooms and four yards.

Tables: `sites`, `hubs`, `lines`, `floors`, `rec_areas`; `cells.floor_id`. Cells without a floor still work (older data, the e2e fixtures), they just do not appear in the grouped dashboard.

## Config

`config/facility.yaml` (versioned like all config): the site name, the seed scales (`demo`: 1 hub, 2 lines, 2 floors, 8 cells; `full`: the target facility), and recreation:

- `rooms_per_line` and `outdoor_rooms_per_line`: day rooms and yards on each line (4 and 4).
- `room_capacity`: most residents in a room at a time (16, a whole floor).
- `max_concurrent_out_per_line`: most floors of a line in the yards at once (4). Day rooms, which carry the baseline out-of-cell time, are limited only by how many day rooms there are, never by this.
- `stagger_minutes`: each floor starts this much after the one below it.

## Seeding

`make seed` builds the small demo facility (32 cells) and puts the 12 synthetic residents in its first cells. `make seed-full` builds the full facility with a resident and a device in 90% of the cells (about 1,730) in a few seconds; it needs an empty database and refuses to run in production. Synthetic data only.

## Recreation by line and floor

For a line, each day's template gives every floor its own recreation blocks: the same slots as the unit template, started `stagger_minutes` apart, pushed later if more blocks of that kind would run at once than the line allows, each in its own room. Programs and visits are shared by every floor. A resident sees and books only their own floor's blocks and the shared ones. Staff can add a block for one floor or for all; adding one that would break the yard limit is refused (`LINE_BUSY`). There is no capacity report: the owner confirmed four yards per line is enough.

## Dashboard

The dashboard groups cells, residents, offline kiosks and residents with a lock by hub, line and floor; a floor opens the roster filtered to it. The roster pages 100 residents at a time and filters by hub, line, floor or a search on code or cell. The device list filters the same way. Numbers come from aggregate queries (see `docs/operations.md` for the measured cost at full size).
