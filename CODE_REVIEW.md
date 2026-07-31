# Code Review — generic-battery-optimizer

*Review date: 2026-07-07, branch `bivalent_operation`.*

Scope: correctness of the optimizer (batteries, EV charging, heat pumps),
bugs, simple improvements, and specifically whether **bivalent heat pump
operation** is modeled correctly.

Bottom line: one bug currently breaks the heat pump feature entirely
(Bug 1), and bivalent operation is **not** modeled correctly (see section
below).

> **Status update (same day):** Bugs 1–4 have been fixed, the bivalent
> operation was reworked (new `max_thermal_power_hp` capacity limit as the
> physically correct mechanism, corrected `bivalent_temp` fallback with a
> configurable `bivalent_heat_fraction`), and the heat pump model was
> linearized into an exact MILP (solves with glpk). The findings below are
> kept as reviewed; items 5, 6 and everything under "Other bugs" remain
> open.

---

## Critical bugs (all verified by running the code)

### 1. `HeatPump` cannot be constructed at all

`validate_electric_power` in `src/battery_optimizer/profiles/heat_pump.py:240`
is a Pydantic v2 `mode="after"` model validator, but it is written with a
`(cls, values)` signature and no `@classmethod`. Pydantic binds the instance
to `cls` and passes a `ValidationInfo` object as `values`, so *every*
`HeatPump(...)` call raises:

```
AttributeError: 'ValidationInfo' object has no attribute 'min_electric_power_hp'
```

This causes the 14 test failures in `tests/helpers/test_model_setup*.py`
(suite result at review time: 14 failed, 127 passed).
Fix: `def validate_electric_power(self) -> "HeatPump":` and use `self.…`,
like the other validators in the same file.

### 2. `interpolate_temperature` corrupts the caller's data

`helpers/heat_pump_profile.py:143` inserts
`temperature[current_period] = None` into the *user's dict* and never writes
the interpolated value back. Verified: the first call for a missing timestamp
returns the interpolated value, the second call returns `None` — and the
profile dict permanently contains a `None`. Any repeated model build (e.g.
rolling horizon) with the same profile object gets `None` temperatures.
Fix: interpolate on a copy (as `interpolate_heat_energy` does via
`pd.Series`).

### 3. `HpLibWrapper.get_cop_values` calls methods that don't exist

`helpers/hplib.py:449-450` calls `get_cop_low_temp`/`get_cop_high_temp`,
which were renamed to `get_cop_flow_temperature`/`get_cop_output_temperature`.
Calling `get_cop_values` raises `AttributeError`.

### 4. Generic heat pump thermal power off by a factor of 10⁶

`helpers/hplib.py:319`: the `p_th` field is documented as **kW**, hplib's
`get_parameters` expects **W** (confirmed in its docstring), and the code
*divides* by 1000. A 10 kW pump arrives at hplib as 0.01 W. It should be
`* 1000`.

### 5. The new examples don't match the current API

`example/example2.py` and `example3.py` construct
`HeatPump(type=..., heat_source_temperature=..., predict_tank_loss=...)` —
all rejected by `extra="forbid"` — pass temperatures in Kelvin (328.15 fails
the `le=200` Celsius check) and omit the required
`cop_output_temperature`/`cop_flow_temperature`. Verified: instant
`ValidationError` with 5 errors. They appear to target a different/older
heat pump interface.

### 6. `export/heat_pump.py` is entirely stale

It iterates `model_block.periods` (the block attribute is `hp_block` now) and
reads variables that no longer exist (`heat_supply_HP`,
`heat_supply_hp_demand`, `heat_supply_hp_tes`, `y_delta_tes_over_value`,
`y_tes_over_value`, `source_temp`). `tes_temperature` also subtracts 273.15
although the model works in °C. `visualize/heat_pump.py` builds on it, so
both modules are dead as-is.

---

## Bivalent operation — not modeled correctly

The constraint (`blocks/heat_pump.py:649-658`) says: if
`outdoor_temp ≤ bivalent_temp`, then
`heat_supply_hp_total ≤ 0.7 · heat_loss_building`. Problems:

- **It caps HP capacity by the demand, not by physics.** In reality a heat
  pump's *thermal capacity* falls with outdoor temperature, and bivalence
  means the capacity curve crosses the demand curve at the bivalent point.
  Here, a large demand lets the HP supply 0.7×demand even if that exceeds its
  real cold-weather capability, while a small demand throttles a pump that
  could easily cover 100%.
- **Discontinuous and wrong at the bivalent point.** One degree above the
  threshold: unlimited. At the threshold: 70%. By definition, *at* the
  bivalence point the HP should just barely cover 100%, degrading gradually
  below it. The 30% backup share is only correct at one specific temperature
  well below the bivalent point.
- **Warm water demand is excluded from the cap basis.**
  `heat_supply_hp_total` also serves `warm_water_demand` and TES charging,
  but the cap is relative to `heat_loss_building` alone. In a cold period
  with only warm-water demand (`heat_loss_building == 0`) the HP is forced
  completely off and everything runs through the COP-1 heating rod. TES
  pre-charging is likewise blocked below the bivalent temperature even when
  the HP has headroom.
- **`bivalent_temp = 0.0 °C` crashes the build.** The validator at
  `profiles/heat_pump.py:349` uses truthiness
  (`if (self.hp_switch_off_temperature or self.bivalent_temp)`), so a value
  of `0.0` — a perfectly realistic bivalent temperature — skips the
  "outdoor_temperature required" check, and block construction then hits
  `block.outdoor_temperature`, which was never created
  (`blocks/heat_pump.py:650`). Use `is not None`. Same for
  `hp_switch_off_temperature = 0.0`.
- The 0.7 is a hard-coded magic number (only documented in the field
  description).

**Recommended formulation:** derive a temperature-dependent maximum thermal
output `P_th_max(T_out)` (hplib's `simulate` returns `P_th`, so the existing
wrapper can produce this per period alongside the COPs) and constrain
`heat_supply_hp_total ≤ P_th_max(T_out)`. The optimizer then discovers the
bivalent split naturally — correctly for both parallel and alternative
operation — and the demand-coupling, discontinuity, and warm-water problems
all disappear.

---

## Other heat pump model issues

- **The model is nonconvex-nonlinear, but the default solver is glpk.**
  `heat_supply_hp_total == electric_power_hp * cop_value`
  (`blocks/heat_pump.py:427`) is a product of two continuous variables, and
  the COP selectors (`(cop_value − cop_high)·y_TES == 0`, lines 387/418) are
  bilinear equalities. Only Gurobi (which the tests require and skip without)
  can solve this. Since `cop_value` only ever takes two known values selected
  by `y_TES`, this can be linearized exactly — e.g. split `electric_power_hp`
  into a flow-temperature part and an output-temperature part and write
  `heat_supply = cop_low·p_flow + cop_high·p_output`. That turns the whole
  model into a MILP solvable by any free solver — the single most valuable
  improvement available.
- **Inconsistent big-M in `discharge_cons`** (line 462): uses
  `max_heat_supply_hp` as the cap for TES discharge, but the variable's own
  bound is `max_heat_supply_tes`. Whichever is smaller silently wins — the M
  should be `max_heat_supply_tes`.
- **Units mismatch in `charge_MIND_cons`** (line 455): compares a *thermal*
  flow against the *electric* minimum power
  (`y_TES·min_electric_power_hp ≤ heat_supply_hp_to_tes`). Should involve
  the COP or act on the electric variable.
- **TES energy balance uses the wrong period length on non-uniform grids**
  (line 784): the *current* period's conversion factor is applied to the
  *previous* period's flows. Currently latent because `add_heat_pump`
  enforces a fixed frequency, but it's a trap.
- Tank losses are ignored in the "TES must hold enough energy for its
  discharge" check (line 560).
- `max_heat_supply_tes` equals `max_heat_energy_tes` numerically
  (`profiles/heat_pump.py:500-519`) — an implicit "full discharge in exactly
  one hour" assumption worth making explicit or configurable.
- Misleading comments: "4.186 # Heat capacity of water in kWh/kgK" (it's
  kJ/(kg·K); the math is right), and the naming `cop_high` = COP *at* high
  temperature = numerically the *lower* COP invites sign errors (the new
  field names `cop_output_temperature`/`cop_flow_temperature` are better —
  finish the migration). Also `10 *` in `max_heat_supply_hp` duplicates
  `MAX_COP`.

---

## Other bugs and simple improvements

- **Shared "random" default names** (`profiles/battery.py:27`,
  `profiles/heat_pump.py:37`): `Field(default=secrets.token_hex(...))` is
  evaluated once at import, so all unnamed batteries/heat pumps in a process
  get the *same* name (verified) and collide when added to one model. Use
  `default_factory=lambda: secrets.token_hex(SECRET_LENGTH)`.
- **Zero-valued Generic parameters rejected** (`helpers/hplib.py:198`):
  `all([self.id, self.t_in, self.t_out, self.p_th])` treats `t_in=0`
  (0 °C — a standard hplib set point) as missing. Use `is not None` checks.
- `parse_profile_stacks.py:86`: `opt_profiles.pop(profile)` should be
  `opt_profiles.pop(name)` — a DataFrame is unhashable, so this error path
  itself raises `TypeError`. Lines 122-125 are a dead loop (builds `columns`,
  converts nothing; `pd.Index.append` doesn't mutate), and `calculate_energy`
  is unused — delete both.
- `export/pandas.py:286` uses `.seconds` instead of `.total_seconds()` —
  wrong power values for period lengths ≥ 24 h.
- `model.py:572-593` (`generate_objective`): the `> 0` is outside `any(...)`,
  so it compares a bool; and `ub=None` (unbounded, which the heat pump
  top-level sink uses) is falsy and excludes the device. It works today only
  by coincidence — mirror the `!= 0` filter from `add_energy_paths` (which
  handles `None` correctly by accident).
- `model.py:693`: stray `print(devices)` — should be `log.debug`.
- `Solver.solve` returns `None` on infeasibility but `optimize()`
  (`__init__.py:99`) ignores the return value and exports anyway — a failed
  solve silently returns garbage frames. Raise, or at least propagate the
  failure.
- EV non-interruptible charging: the `is_charging == 1` anchor
  (`blocks/ev.py:292`) only fires if `charge_start_time` is exactly an index
  element. `ProfileStackProblem` inserts it, but direct `Model.add_ev` users
  with a between-timestamps start time silently lose the "must start
  immediately" behavior — the charge window can then float. Also, forcing
  charging at the start time even when the EV is already at `max_soc` plus
  `min_charge_power > 0` can make the model infeasible.
- The uncommitted change in `helpers/hplib.py` comments out the °C sanity
  check for time-series inputs rather than fixing whatever was wrong with it;
  the dict-length mismatch just above it also reuses the wrong "must be of
  the same type" message. Note `MINIMUM_KELVIN = 200` is really a "max
  plausible Celsius" constant — the name is actively confusing.
- Minor: `interpolate_heat_energy` handles `float` but not `int` scalars (an
  `int` falls through to `current_period in heat_demand` → `TypeError`).

---

## Suggested fix order

1. The pydantic validator (Bug 1) — unblocks the whole heat pump feature and
   the 14 failing tests.
2. The interpolation mutation (Bug 2).
3. The bivalent reformulation (capacity-based).
4. The COP linearization (MILP) — removes the Gurobi dependency.
