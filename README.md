# Eaton ePDU G3 for Home Assistant

[![HACS: custom repository](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/LavenderFox2430/ha-eaton-epdu/actions/workflows/validate.yml/badge.svg)](https://github.com/LavenderFox2430/ha-eaton-epdu/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A custom integration for Eaton **ePDU G3** rack PDUs (EMAT/EMAB/EMAH/EMIT/…,
the "Marlin" generation) over SNMP. One config entry covers the whole daisy
chain: every unit becomes its own Home Assistant device, every switched outlet
becomes a switch, and everything the MIB exposes becomes a sensor.

Developed and verified against two daisy-chained **EMAT08-10** units
(ePDU MA 1U, 8 × NEMA 5-15R, firmware 06.00.0003) with an environmental probe
on the host unit.

## What you get

**One device per PDU on the chain.** Downstream units are linked to the host
in the device tree, so the chain is visible at a glance. Adding a PDU needs no
configuration: its rows appear in the next poll and its entities are created
on the spot.

**Per outlet** (each named as it is named on the PDU, e.g. `Outlet A1`):

- Switch (on/off), power-cycle button, energy-reset button
- Current, power, apparent power, reactive power, power factor, energy
- Status, and — off by default — capacity, thresholds, crest factor,
  power-on state, sequence delay, reboot-off time, shutoff delay, switchable

**Per input / feed:**

- Voltage, current, load %, frequency, power, apparent power, reactive power,
  power factor, energy, and per-input totals with their own energy counter
- Threshold statuses; configured warning/critical limits off by default

**Per group / section:** voltage, status, and a switch (disabled by default,
since it cuts every outlet in the section).

**Environment**, per unit: temperature, humidity and dry contacts, plus an
`Environment` summary sensor.

**Chain diagnostics:** units present, unit count, per-unit part number, serial,
firmware, unit type, device clock, SNMP agent uptime, and the communication /
internal / strapping status of each unit — which is how you notice a
daisy-chained PDU has dropped off.

On the reference hardware that is **192 entities enabled by default**, out of
586 available once the disabled diagnostics are switched on — which is every
single OID those units expose, with nothing left unmapped.

### Outlet names follow the PDU

The PDU has no field for "what is plugged in here", but it does let you name
each outlet. Name one on the PDU (**Settings → Outlets**) after its load and
the integration picks it up on the next poll, with the position kept in front
so the physical socket stays identifiable:

| Name set on the PDU | Entities become |
|---|---|
| `Outlet A1` (factory) | `Outlet A1`, `Outlet A1 Power`, … |
| `Firewall` | `Outlet A1 (Firewall)`, `Outlet A1 (Firewall) Power`, … |

That covers the switch, the power-cycle and energy-reset buttons, and every
statistic for that outlet — they all inherit the outlet's label. An outlet
still carrying its factory name gets no empty brackets, and a name that just
repeats the position (`A1`) is ignored rather than doubled up.

Renaming an outlet later updates the friendly names; entity IDs keep whatever
they were created with, as Home Assistant always does.

### Energy counters are trip meters

Every Wh counter has a **Reset energy** button, because the Eaton Wh objects
are writable for exactly this purpose: writing 0 zeroes the counter *and*
restarts its timestamp, on the PDU itself. It is the same reset the PDU's own
web UI performs — not a Home Assistant-side offset — so the new zero applies
to anything else polling that PDU.

- `Outlet A1 Reset energy` … one per outlet
- `Feed A Reset energy` (per phase) and `Feed A Reset total energy` (per input)
- `Reset all energy counters` — one per PDU, clears every counter on that unit
  (10 of them on an EMAT08-10)

The buttons sit in the device page's **Configuration** section. There is no
undo: the previous total is gone from the hardware. Home Assistant's own
long-term statistics are unaffected — the energy sensors are
`total_increasing`, so a reset to 0 is recognised as a counter restart rather
than as negative consumption, and the Energy dashboard keeps its history.

### Missing modules report N/A

"Not installed" and "zero" are different things, and this integration keeps
them apart. A G3 reports a humidity of `0` and a threshold status of `good`
for a probe that is not connected — those readings are suppressed:

| | Unit with a probe | Unit without one |
|---|---|---|
| `Environment` | `connected` | **`N/A`** |
| `Temperature` | `22.2 °C` | unknown |
| `Humidity` | `48.0 %` | unknown |
| `Threshold status` | `good` | **`N/A`** |
| `Contact 1` | `off` (open) | unknown |

The `Environment` sensor's attributes list every probe the unit says it should
have, against what it can actually read:

```yaml
temperature_expected: 1
temperature_connected: 0
temperature:
  Temperature probe 1: N/A
contact_expected: 2
contact_connected: 0
contact:
  Contact 1: N/A
  Contact 2: N/A
```

Any text sensor that cannot be read shows `N/A`. Numeric sensors go to
*unknown*, which is what Home Assistant needs in order not to plot a fake 0.

## Requirements

- Home Assistant 2024.12 or newer
- SNMP enabled on the PDU. `pysnmp` is installed automatically.

## Installation

### HACS (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=LavenderFox2430&repository=ha-eaton-epdu&category=integration)

Or by hand: **HACS → ⋮ → Custom repositories**, add
`https://github.com/LavenderFox2430/ha-eaton-epdu` with category **Integration**,
then install it and restart Home Assistant.

### Manually

Copy `custom_components/eaton_epdu/` into your `/config/custom_components/`
folder and restart Home Assistant.

## Enable SNMP on the PDU

In the ePDU web UI: **Settings → Network → SNMP**.

G3 firmware offers **SNMPv1** and **SNMPv3**. Prefer v3 — v1 sends its
community in clear text, and on a G3 the v1 community doubles as the write
password for outlet switching.

For SNMPv3, create a user and note three things: the user name, the security
level (`noAuthNoPriv` / `authNoPriv` / `authPriv`) and the protocols. G3 uses
**SHA** for authentication and AES/DES for privacy. Give the user **read/write**
access if you want outlet control — read-only is enough for monitoring.

Check it from any machine before touching Home Assistant:

```bash
pip install pysnmp
python tools/epdu_dump.py 192.168.1.96 --v3 --user HomeAssistant --auth-key 'your-password'
```

That prints the device identity, every table it found and every column in it,
and writes the full walk to `epdu_dump.json`.

## Configuration

**Settings → Devices & Services → Add Integration → Eaton ePDU G3**, then:

1. Host, port (161) and SNMP version.
2. Credentials — community strings for v1/v2c, or user/protocols/passwords for
   v3. For `authNoPriv`, set the privacy protocol to `none`.

Only the host PDU's address is needed; daisy-chained units come in over the
same session.

### Options

| Option | Default | Notes |
|---|---|---|
| Polling interval | 30 s | The whole subtree is read in one walk. |
| SNMP timeout / retries | 5 s / 2 | |
| GETBULK max repetitions | 25 | Ignored on SNMPv1, which has no GETBULK — expect a slower poll there. |
| Delay before re-reading after a switch command | 3 s | Gives the PDU time to actually switch before the state is re-read. |
| Temperature unit reported by the PDU | auto | See below. |
| Create sensors for unmapped MIB columns | off | A diagnostic sensor per column this integration does not name, each with its OID as an attribute. |

### Temperature scale

The G3 reports temperatures in tenths of **whatever scale the unit is set
to** — the raw value `719` is 71.9 °F on a Fahrenheit unit and 71.9 °C on a
Celsius one. The integration reads the unit's own `temperatureScale` setting
(one per PDU, so a mixed chain works), and falls back to the absolute-zero
sentinel an unconnected probe reports — `-4595` (−459.5 °F) or `-2731`
(−273.1 °C) — on firmware that does not expose it. Set the scale explicitly
in the options if it ever guesses wrong.

## Energy dashboard

Outlet, input and input-total energy sensors are `total_increasing` with the
energy device class, so they can be added as individual devices under
**Settings → Dashboards → Energy**. Use the per-outlet ones to attribute
consumption, or the input total for the PDU as a whole. Note that the input
per-phase counter and the input total counter have separate reset times and
will not match.

## Services

| Service | What it does |
|---|---|
| `eaton_epdu.outlet_on` | Switch on, optionally after `delay` seconds |
| `eaton_epdu.outlet_off` | Switch off, optionally after `delay` seconds |
| `eaton_epdu.outlet_cycle` | Power cycle, using the PDU's reboot-off time |
| `eaton_epdu.dump_oids` | Walk the PDU and write every OID to `config/eaton_epdu_dump_<host>.json` |

```yaml
action: eaton_epdu.outlet_cycle
target:
  entity_id: switch.epdu_01_outlet_a3
data:
  delay: 5
```

The delay is handled by the PDU itself, not by Home Assistant: the command
column is written with the delay in seconds, so it still fires even if Home
Assistant restarts in between.

## How it works

Rather than reading a fixed list of OIDs, the integration walks
`1.3.6.1.4.1.534.6.6.7` once per poll and classifies every OID it gets back
against the table map in `custom_components/eaton_epdu/oids.py`. So:

- Anything your firmware exposes is fetched, named or not.
- Extra units, outlets, phases or probes need no code changes — they are
  index tuples that appear in the walk.
- A wrong column number in the map costs a name or a unit, never the data.

Every column is checked against two sources: the published **EATON-EPDU-MIB**
(revision 202303311500Z), which supplies the object names, enumerations and
which objects are writable, and a live walk of the reference hardware.
`docs/OID_MAP.md` records both, column by column, and each column in
`oids.py` carries its MIB object name.

## Troubleshooting

**"No SNMP response"** — SNMP is not enabled, the port is wrong, or the PDU
restricts which hosts may query it. `Test-NetConnection`/`ping` only proves the
network path; use the dump tool to prove SNMP.

**"The PDU rejected these credentials"** — usually the wrong auth protocol.
G3 uses SHA; MD5 fails with *Wrong SNMP PDU digest*. Check the security level
too: an `authNoPriv` user must have the privacy protocol set to `none`.

**Switching fails but sensors work** — the SNMP user is read-only. Give it
read/write on the PDU (or set a write community for v1/v2c).

**A value is missing or looks wrong** — download diagnostics from the
integration page. It contains the parsed model *and* the complete raw walk, so
the OID behind any number is right there. Turn on the unmapped-columns option
to see the rest.

## Licence

MIT.

## Trademarks

Eaton and ePDU are trademarks of Eaton Corporation. This is an unofficial,
community-built integration, not affiliated with or endorsed by Eaton. The
brand images in `custom_components/eaton_epdu/brand/` are used only to identify
the hardware this integration talks to, and come from two places:

- `icon.png` / `icon@2x.png` — the favicon an ePDU G3 serves from its own web
  interface, upscaled from the 64×64 original.
- `logo.png` / `logo@2x.png` — the Eaton wordmark from Wikimedia Commons
  ([File:2017 Eaton logo.png](https://commons.wikimedia.org/wiki/File:2017_Eaton_logo.png)),
  which hosts it as public domain: a plain text wordmark falls below the
  threshold of originality for copyright. Copyright and trademark are separate,
  though — the mark remains Eaton's.

Neither is recoloured or redrawn, only trimmed and scaled. Regenerate both with
`python tools/make_brand_images.py`.
