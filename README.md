# Charge Ahead

Home Assistant integration that makes sure your car is charged in time for the
next trip in a calendar.

Each calendar event with a location is a trip. Charge Ahead determines the
travel time from home to the location, subtracts a configurable buffer and
derives the departure time. From the distance (outbound and return) plus a
reserve it computes the target state of charge. The plan is then handed to a
target of your choice, for example [evcc](https://evcc.io).

Charge Ahead does not optimise *when* to charge. That stays with your charge
controller (evcc or similar).

> **Status:** early development (0.x). Configuration and behaviour may still change.

## How it works

1. Reads the trip calendar for the next days (`calendar.get_events`). A trip is
   any timed event with a location; all-day events, events without a
   location and online events ("Online", meeting links) are ignored. The next upcoming trip is planned.
2. Routes from your home zone to the location with the **Google Maps Travel
   Time** or **Waze Travel Time** integration (one of them must be set up).
   Locations with a place name and the address on separate lines (Apple
   Calendar) are retried with the address line only.
3. Computes
   - departure = event start − travel time − buffer
   - energy = distance × 2 × consumption
   - target SoC = energy / battery capacity + reserve, rounded up to the SoC step
4. Writes the plan to the target once it changes, and runs the clear action if
   the trip disappears before departure.
5. Sends a notification when the target SoC is above the charge limit, above
   100 %, when the departure has already passed, when the location cannot be
   routed or when the target fails. Each notification is sent once per trip.

Consumption is derived from the car's own range estimate when state of charge
and range entities are configured, otherwise the fixed value is used.

The calendar is read every update interval (default 15 minutes) and whenever
the calendar entity changes.

## Entities

| Entity | Content |
|---|---|
| Status | `planned`, `no_trip`, `departure_passed`, `routing_failed`, `vehicle_data_missing`, `target_failed`; attributes `warnings`, `error`, `consumption_kwh_per_100km` |
| Departure | Planned departure time |
| Target SoC | Target state of charge in % |
| Energy needed | Energy for the round trip in kWh |
| Distance | One-way distance in km |
| Travel time | One-way travel time in minutes |
| Next trip | Event summary; attributes `start`, `location` |

## Plan targets

| Target | What happens |
|---|---|
| None | The plan is only exposed as sensors (planned). |
| Entities | Target SoC goes to a `number`/`input_number`, departure to a `datetime`/`input_datetime`. |
| Actions | Your own action sequence runs with the variables `target_soc`, `departure` (ISO 8601 with offset), `departure_local` (local time, `YYYY-MM-DD HH:MM:SS`) and `energy_kwh`. |

### Example: evcc

With the [evcc integration](https://github.com/marq24/ha-evcc), choose
**Run actions** and use:

```yaml
action: evcc_intg.set_vehicle_plan
data:
  vehicle: "db:1"
  soc: "{{ target_soc }}"
  startdate: "{{ departure_local }}"
```

The evcc integration only accepts `YYYY-MM-DD HH:MM:SS` in local time, hence
`departure_local`. It reports errors in its response instead of raising them,
so a wrong value fails silently. To surface such errors, capture the response:

```yaml
- action: evcc_intg.set_vehicle_plan
  data:
    vehicle: "db:1"
    soc: "{{ target_soc }}"
    startdate: "{{ departure_local }}"
  response_variable: evcc_response
- if: "{{ 'error' in evcc_response }}"
  then:
    - stop: "evcc rejected the plan"
      error: true
```

Clear action:

```yaml
action: evcc_intg.del_vehicle_plan
data:
  vehicle: "db:1"
```

## Installation

Requires Home Assistant 2026.11 or newer.

1. **Settings → Marketplace → Add from link**, enter
   `https://github.com/FariSoftware/charge-ahead`, category **Integration**.
2. Download **Charge Ahead**.
3. **Settings → Devices & services → Add integration → Charge Ahead**.

## Testing a target

**Settings → Tools → Actions**, run `charge_ahead.apply_plan` with your entry,
a target SoC and a departure time. Check that the target received the values.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff
.venv/bin/pytest
```

## License

MIT, see [LICENSE](LICENSE).
