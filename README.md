<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/charge_ahead/brand/dark_logo.png">
    <img src="custom_components/charge_ahead/brand/logo.png" alt="Charge Ahead" width="420">
  </picture>
</p>

<p align="center">
  Your car, charged in time for the next trip in your calendar.
</p>

---

Charge Ahead is a Home Assistant integration that reads your trips from a
calendar, works out when you have to leave and how much charge the trip
needs, and hands that plan to your charge controller, for example
[evcc](https://evcc.io).

Put an event with a location into the calendar, from your phone or anywhere
else. Charge Ahead does the rest:

- **Departure** = event start − travel time − buffer
- **Target SoC** = energy for the round trip ÷ battery capacity + reserve
- The plan goes to evcc (or any other target), is updated when the trip
  changes and removed when the trip is cancelled.

Charge Ahead does not decide *when* to charge. Solar surplus, cheap hours and
the actual charging stay with your charge controller.

> **Status:** early development (0.x). Configuration and behaviour may still
> change between versions.

## Features

- Any Home Assistant calendar as trip source (CalDAV/iCloud, Google, local, …)
- Routing via the **Google Maps Travel Time** or **Waze Travel Time**
  integration
- Consumption derived from the car's own range estimate, so cold weather is
  taken into account
- **Follow-up trips:** if the time at home between two trips is too short to
  recharge, the first departure already carries enough energy for both
- Built-in **evcc** target; alternatively entities or your own actions
- Notifications when the plan exceeds the charge limit or the battery, when a
  location cannot be found, or when the target rejects the plan
- Sensors for departure, target SoC, energy, distance, travel time and status

## Requirements

- Home Assistant **2026.11** or newer
- A calendar entity with your trips
- The Google Maps Travel Time integration (needs an API key) or the Waze
  Travel Time integration
- For the evcc target: the [evcc integration](https://github.com/marq24/ha-evcc)
  by marq24

## Installation

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FariSoftware&repository=charge-ahead&category=integration)

Or manually:

1. **Settings → Marketplace → Add from link**, enter
   `https://github.com/FariSoftware/charge-ahead`, category **Integration**.
2. Download **Charge Ahead** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Charge Ahead**.

## Configuration

The setup walks through five steps. Everything can be changed later under
**Configure**.

| Step | What you set |
|---|---|
| **Trips** | Name and the calendar that holds your trips |
| **Routing** | Google Maps or Waze, the home zone (start of every trip) |
| **Vehicle** | Battery capacity, state of charge, range, consumption, charge limit, charging power at home. Prefilled from evcc if it is installed. |
| **Planning** | Departure buffer, reserve on return, SoC step, look-ahead, update interval, notifications |
| **Target** | Where the plan goes (see below) |

### Plan targets

| Target | What happens |
|---|---|
| **evcc** | Sets a one-time charging plan (target SoC and departure) for the chosen vehicle and deletes it when the trip is gone. Repeating plans in evcc stay untouched. Offered when the evcc integration is installed. |
| **Entities** | Writes the target SoC into a `number`/`input_number` and the departure into a `datetime`/`input_datetime`. |
| **Actions** | Runs your own action sequence with the variables `target_soc`, `departure` (ISO 8601 with offset), `departure_local` (local time, `YYYY-MM-DD HH:MM:SS`) and `energy_kwh`. |
| **None** | Only provides the sensors, for your own automations. |

<details>
<summary>Example: evcc through custom actions</summary>

The built-in evcc target covers this. Use actions only if you need something
different. Templates only work in YAML mode of the action editor.

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

The evcc integration reports errors in its response instead of raising them,
hence the check. Clear action:

```yaml
action: evcc_intg.del_vehicle_plan
data:
  vehicle: "db:1"
```

</details>

### Notifications

Enter a notify entity (`notify.my_phone`) or a notify action
(`notify.mobile_app_iphone`) in the planning step. Each message is sent once
per trip, in German or English depending on the Home Assistant language.

## How trips are planned

A **trip** is a calendar event with a start time and a location. All-day
events, events without a location and online events ("Online", "Teams",
meeting links) are ignored. Charge Ahead plans the next upcoming trip.

Locations that hold a place name and the address on separate lines, as Apple
Calendar stores them, are retried with the address line alone if the full
text cannot be routed.

**Example:** a meeting at 11:00, 33 km away, 52 minutes by car, 15 minutes
buffer, 15.8 kWh/100 km, 56 kWh battery, 20 % reserve:

- departure: 11:00 − 52 min − 15 min = **09:53**
- energy: 2 × 33 km × 15.8 kWh/100 km = 10.4 kWh = 19 % of the battery
- target SoC: 19 % + 20 % = **39 %**

**Follow-up trips.** If you are back at 12:52 and leave for the next trip at
13:00, there is no time to recharge. Charge Ahead works backwards through the
following trips: before each trip the battery must hold that trip's energy
plus whatever the next trip lacks after recharging at home in between (based
on the charging power), and never less than the reserve. Trips are only
followed while the time at home would not allow a full charge, at most five.

The calendar is read every update interval (default 15 minutes) and whenever
the calendar entity changes. A plan is written only when it changes; it is
remembered across restarts so a cancelled trip is always cleaned up.

## Entities

| Entity | Content |
|---|---|
| Status | `planned`, `no_trip`, `departure_passed`, `routing_failed`, `vehicle_data_missing`, `target_failed`; attributes: warnings, error, consumption, follow-up trips included |
| Departure | Planned departure time |
| Target SoC | Target state of charge in % |
| Energy needed | Energy needed at departure above the reserve, in kWh |
| Distance | One-way distance in km |
| Travel time | One-way travel time in minutes |
| Next trip | Event title; attributes start and location |
| Resend plan | Button: writes the current plan to the target again, e.g. after it was deleted there |

## Actions

| Action | Purpose |
|---|---|
| `charge_ahead.apply_plan` | Write a given SoC and departure to the configured target. Useful to test a target. |
| `charge_ahead.clear_plan` | Run the target's clear step. |

## Limitations

- One vehicle per entry. Add another entry for a second car.
- Every trip is assumed to start and end at home.
- Travel time is the current estimate when planning, not a forecast for the
  departure time.
- With the evcc target, Charge Ahead uses the vehicle's one-time plan and
  overwrites a one-time plan set by hand.

## Troubleshooting

- **Status `routing_failed`:** the location could not be routed. Check the
  location text; with Waze, check the region.
- **Plan missing in the charge controller:** press **Resend plan**.
- **Debug logging:** **Settings → Devices & services → Charge Ahead → ⋮ →
  Enable debug logging**, reproduce the problem, then disable it again to
  download the log.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff
.venv/bin/ruff check . && .venv/bin/pytest
```

The planner core (`planner.py`) has no Home Assistant dependency and is tested
on its own.

## License

[MIT](LICENSE) © Fari Software GmbH
