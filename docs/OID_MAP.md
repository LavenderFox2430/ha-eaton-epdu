# EATON-EPDU-MIB column map

Base OID: `1.3.6.1.4.1.534.6.6.7` (also the `sysObjectID` of a G3).

Two independent sources back this map:

1. The published **EATON-EPDU-MIB**, revision `202303311500Z` — every column
   name, enumeration and access mode below comes from it. Each column in
   `oids.py` carries its MIB object name in a `mib=` field.
2. A live walk of two daisy-chained **EMAT08-10** units (ePDU MA, 1U,
   8 × NEMA 5-15R, firmware 06.00.0003, environmental probe on the host),
   captured with `tools/epdu_dump.py`. Observed values are quoted below.

On that hardware the two agree completely: **every OID the PDU returns is
mapped**, with nothing left over.

The integration never depends on this map to *fetch* data — it walks the whole
subtree. The map supplies names, units, scaling and write targets.

## Index structure

Every table is indexed by `unitIndex` first:

| Table | Index |
|---|---|
| unit, unitControl, outletShutoff | `(unit)` |
| input, inputTotal, group\*, outlet\* | `(unit, n)` |
| inputVoltage / inputCurrent / inputPower | `(unit, input, phase)` |
| temperature, humidity, contact | `(unit, probe)` |

A stand-alone G3 is unit `0`; with daisy-chaining the host stays `0` and
downstream units are `1..N`. `unitsPresent` (`.1.1.0`, a scalar) lists them —
observed `"0,1"`.

## Writable objects

These are the only objects the integration ever writes, and the only ones it
can write:

| OID | MIB object | ASN.1 type | Used by | Value written |
|---|---|---|---|---|
| `.6.6.1.3.<u>.<o>` | outletControlOffCmd | Integer32 | outlet switch off | delay in seconds, 0 = now |
| `.6.6.1.4.<u>.<o>` | outletControlOnCmd | Integer32 | outlet switch on | delay in seconds, 0 = now |
| `.6.6.1.5.<u>.<o>` | outletControlRebootCmd | Integer32 | power-cycle button | delay in seconds, 0 = now |
| `.5.6.1.3/.4/.5.<u>.<g>` | groupControl\*Cmd | Integer32 | group switch/button | as above |
| `.3.4.1.5.<u>.<i>.<p>` | **inputWh** | **Unsigned32** | "Reset energy" | `0` |
| `.3.5.1.5.<u>.<i>` | **inputTotalWh** | **Unsigned32** | "Reset total energy" | `0` |
| `.5.5.1.4.<u>.<g>` | **groupWh** | **Unsigned32** | "Reset energy" | `0` |
| `.6.5.1.4.<u>.<o>` | **outletWh** | **Unsigned32** | "Reset energy" | `0` |

**The type matters.** Agents enforce it: sending an `Integer32` to a column
declared `Unsigned32` is refused with `wrongType`, and vice versa. Each column
records its type in `write_syntax`, and the client retries once with the other
integer type if the agent disagrees with the MIB.

The Wh objects are `read-write` precisely so they can be zeroed; the MIB says
so outright: *"This object is writable so that it can be reset to 0. When it
is written to, the ... Timer will be reset as well."* That is the trip-meter
behaviour — the counter and its start timestamp both restart, on the hardware.

`unitControlOffCmd` / `unitControlOnCmd` (`.1.3.1.2` / `.3`) are **deliberately
not mapped**: writing to them powers down an entire PDU.

## unitTable — `.1.2.1`

| Col | MIB object | Key | Access | Observed |
|---|---|---|---|---|
| 2 | productName | product_name | ro | `ePDU MA 1U IN: 5-15P 12A 1P OUT: 8X5-15R` |
| 3 | partNumber | part_number | ro | `EMAT08-10` → HA device model |
| 4 | serialNumber | serial_number | ro | `G624K26122` / `G624L20091` |
| 5 | firmwareVersion | firmware_version | ro | `06.00.0003` |
| 6 | unitName | name | rw | `ePDU-01` / `ePDU-02` → HA device name |
| 7 | lcdControl | lcd_control | rw | `0` notApplicable |
| 8 | clockValue | device_time | rw | DateAndTime → 2026-09-20 14:18:23-08:00 |
| 9 | **temperatureScale** | temperature_scale | rw | `1` = **fahrenheit** |
| 10 | unitType | unit_type | ro | `3` = managed |
| 11 | systemType | system_type | ro | `1` = g3ePDU |
| 20–22 | inputCount / groupCount / outletCount | \*_count | ro | `1`, `1`, `8` |
| 23–25 | temperatureCount / humidityCount / contactCount | \*_count | ro | `1`, `1`, `2` |
| 30 | communicationStatus | communication_status | ro | `0` good |
| 31 | internalStatus | internal_status | ro | `0` good |
| 32 | strappingStatus | strapping_status | ro | `0` good |

Columns 30–32 are on by default: on a daisy chain they are how you notice a
unit has dropped off. Columns 23–25 drive the environment summary's
"expected vs connected" comparison.

## inputTable — `.3.1.1`

| Col | MIB object | Key | Observed |
|---|---|---|---|
| 2 | inputType | input_type | `1` singlePhase |
| 3 | inputFrequency | frequency | `600` → ×0.1 → 60.0 Hz |
| 4 | inputFrequencyStatus | frequency_status | `0` good (enum is good/outOfRange, *not* the threshold enum) |
| 5–7 | inputVoltageCount / inputCurrentCount / inputPowerCount | \*_count | `1` each |
| 8 | inputPlugType | plug_type | `120` = nema515 |
| 9 | inputFeedColor | feed_color | `3831236` (0x3A76C4) |
| 10 | inputFeedName | name | `Feed A` → labels every input measurement |

## inputVoltageTable — `.3.2.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | inputVoltageMeasType | `1` singlePhase |
| 3 | **inputVoltage** | `118130` mV |
| 4 | inputVoltageThStatus | `0` good |
| 5–8 | ThLowerWarning / ThLowerCritical / ThUpperWarning / ThUpperCritical | `95000`, `90000`, `130000`, `140000` mV |

## inputCurrentTable — `.3.3.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | inputCurrentMeasType | `1` |
| 3 | inputCurrentCapacity | `12000` mA (the 12 A rating) |
| 4 | **inputCurrent** | `6106` mA |
| 5 | inputCurrentThStatus | `0` |
| 6–9 | the four thresholds | `0`, `-1`, `9600`, `12000` mA (`-1` = disabled) |
| 10 | inputCurrentCrestFactor | `1528` → ×0.001 → 1.53 |
| 11 | inputCurrentPercentLoad | `50` % |
| 12 | inputPhaseDesignator | `L1` |

## inputPowerTable — `.3.4.1` (per phase)

| Col | MIB object | Observed |
|---|---|---|
| 2 | inputPowerMeasType | `1` phase1 |
| 3 | inputVA | `721` VA |
| 4 | inputWatts | `716` W |
| 5 | **inputWh** (rw) | `19891138` Wh |
| 6 | inputWhTimer | `0` — never reset |
| 7 | inputPowerFactor | `1000` → ×0.001 |
| 8 | inputVAR | `-82` var |

## inputTotalPowerTable — `.3.5.1` (per input)

| Col | MIB object | Observed |
|---|---|---|
| 3 | inputTotalVA | `714` VA |
| 4 | inputTotalWatts | `716` W |
| 5 | **inputTotalWh** (rw) | `9787062` Wh |
| 6 | inputTotalWhTimer | `1702825028` → 2023-12-17 |
| 7 | inputTotalPowerFactor | `993` |
| 8 | inputTotalVAR | `-82` var |
| 9 | inputPowerCapacity | `1440` VA (12 A × 120 V) |

Note the per-phase and per-input counters are separate and have separate
reset times, so `inputWh` and `inputTotalWh` legitimately differ.

## groupTable — `.5.1.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | groupID | `"1"` |
| 3 | groupName | `Section A` |
| 4 | groupType | `4` outletSection |
| 5 | groupBreakerStatus | `0` notApplicable (no section breaker on this model) |
| 6 | groupChildCount | `8` |
| 7 | groupColor | `16051527` |
| 8 | groupDesignator | `A` |
| 9 | groupInputIndex | `1` |

`.5.2.1` is `groupChildTable` (groupChildType / groupChildOID) — a
relationship table, so no entities are built from it.

## groupVoltageTable `.5.3.1` / groupCurrentTable `.5.4.1` / groupPowerTable `.5.5.1`

Only the voltage table exists on an EMAT08-10 (observed `118150` mV). All
three follow the MIB exactly:

- voltage: 2 measType, **3 groupVoltage**, 4 ThStatus, 5–8 thresholds
- current: 2 capacity, **3 groupCurrent**, 4 ThStatus, 5–8 thresholds,
  9 crest factor, 10 percent load
- power: 2 groupVA, 3 groupWatts, **4 groupWh (rw)**, 5 groupWhTimer,
  6 groupPowerFactor, 7 groupVAR

## groupControlTable — `.5.6.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | groupControlStatus | `1` on — enum off/on/rebooting/**mixed** |
| 3–5 | Off / On / Reboot Cmd (rw) | `-1` idle |

Group switches exist but are **disabled by default**: switching a group cuts
every outlet in it.

## outletTable — `.6.1.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | outletID | `"1"` |
| 3 | outletName | `Outlet A1` → the HA entity name |
| 4 | outletParentCount | `1` |
| 5 | outletType | `20` = nema515 (receptacle type) |
| 6 | outletDesignator | `A1` |
| 7 | outletPhaseID | `1` singlePhase |

`.6.2.1` is `outletParentTable` (outletParentType / outletParentOID) — a
relationship table, not used for entities.

## outletVoltageTable — `.6.3.1`

Not present on an EMAT08-10 (this model does not meter outlet voltage), but
mapped from the MIB: **2 outletVoltage**, 3 ThStatus, 4–7 thresholds. Note
this is one column *earlier* than the input and group voltage tables — there
is no measurement-type column.

## outletCurrentTable — `.6.4.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | outletCurrentCapacity | `12000` mA |
| 3 | **outletCurrent** | `445` mA |
| 4 | outletCurrentThStatus | `0` |
| 5–8 | the four thresholds | `0`, `-1`, `9600`, `12000` mA |
| 9 | outletCurrentCrestFactor | `1579` |
| 10 | outletCurrentPercentLoad | `-1` — not computed per outlet on this model |

Capacity is column **2** here but column **3** in the input table.

## outletPowerTable — `.6.5.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | outletVA | `52` VA |
| 3 | outletWatts | `51` W |
| 4 | **outletWh** (rw) | `1178507` Wh |
| 5 | outletWhTimer | `1702825138` |
| 6 | outletPowerFactor | `-981` (negative = leading) |
| 7 | outletVAR | `-9` var |

## outletControlTable — `.6.6.1`

| Col | MIB object | Observed |
|---|---|---|
| 2 | **outletControlStatus** | `1` — off(0) on(1) pendingOff(2) pendingOn(3) |
| 3 | outletControlOffCmd (rw) | `-1` idle |
| 4 | outletControlOnCmd (rw) | `-1` |
| 5 | outletControlRebootCmd (rw) | `-1` |
| 6 | outletControlPowerOnState (rw) | `2` lastState |
| 7 | outletControlSequenceDelay (rw) | `1..8` s, staggered per outlet |
| 8 | outletControlRebootOffTime (rw) | `10` s |
| 9 | outletControlSwitchable (rw) | `1` switchable |
| 10 | outletControlShutoffDelay (rw) | `120` s |

`.6.7.1.2` is `outletAutomaticShutoff` (per unit, observed `0`
notApplicable).

## temperatureTable — `.7.1.1`

| Col | MIB object | Unit 0 | Unit 1 (no probe) |
|---|---|---|---|
| 2 | temperatureName | `""` | `""` |
| 3 | temperatureProbeStatus | `1` connected | `0` disconnected |
| 4 | **temperatureValue** | `719` | `-4595` |
| 5 | temperatureThStatus | `0` | `0` |
| 6–9 | the four thresholds | `500`, `410`, `1220`, `1490` | same |

**Temperatures are in tenths of the scale the unit is configured for**, given
by `temperatureScale` (unitTable column 9) — `1` = Fahrenheit on this pair.
So `719` = 71.9 °F = 22.2 °C, and the thresholds `41 / 50 / 122 / 149 °F` are
Eaton's `5 / 10 / 50 / 65 °C` defaults converted.

`temperatureScale` is read per unit and is authoritative. Where firmware does
not expose it, the integration falls back to the absolute-zero sentinel an
unconnected probe reports: `-4595` (−459.5 °F) or `-2731` (−273.1 °C).

## humidityTable — `.7.2.1`

Same layout; column 4 is tenths of a percent (`480` = 48.0 %). A unit with no
probe reports `0` with `humidityProbeStatus = 0`, which is why every reading
in a row is suppressed when the probe status is not `connected`.

## contactTable — `.7.3.1`

| Col | MIB object | Unit 0 | Unit 1 (no probe) |
|---|---|---|---|
| 2 | contactName | `Contact 1` | `Contact 1` |
| 3 | contactProbeStatus | `1` connected | `0` disconnected |
| 4 | contactState | `0` contactOpen | `-1` contactBad |

## Re-checking this on your own firmware

```bash
pip install pysnmp
python tools/epdu_dump.py 192.168.1.96 --v3 --user <user> --auth-key <password>
```

Or, with the integration running, call the `eaton_epdu.dump_oids` service or
download diagnostics from the integration page — both contain the full raw
walk. To surface a column this map does not name, turn on **Create sensors
for unmapped MIB columns** in the options; each such sensor carries its OID
as an attribute.

The MIB itself is published by Eaton and mirrored by, among others, LibreNMS
at `mibs/eaton/EATON-EPDU-MIB`.
