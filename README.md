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

> **Status:** early development. The planner is not implemented yet. The current
> version contains the configuration flow and the plan targets, so a target can
> be tested with the `charge_ahead.apply_plan` action.

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
