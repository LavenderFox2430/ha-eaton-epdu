# Changelog

All notable changes to this integration are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-20

First release.

### Added

- Config flow for SNMP v1, v2c and v3 (user, auth and privacy protocols,
  optional separate write community).
- One Home Assistant device per unit on the daisy chain, downstream units
  linked to the host. New units are picked up on the next poll, with no
  reconfiguration.
- Sensors for every value the EATON-EPDU-MIB exposes: input and outlet
  voltage, current, load, power, apparent and reactive power, power factor,
  energy and per-input totals; frequency; group voltage and status;
  temperature, humidity and dry contacts; unit part number, serial, firmware,
  clock, and communication/internal/strapping status.
- Switches and power-cycle buttons for every switchable outlet, plus group
  switches (disabled by default).
- Energy reset buttons: one per Wh counter and one per unit, writing 0 to the
  Eaton Wh objects so the counter and its timer restart on the hardware.
- N/A handling: readings from an environmental probe that is not connected are
  suppressed rather than reported as 0, and a per-unit `Environment` sensor
  summarises expected versus readable probes.
- Automatic detection of the temperature scale from each unit's
  `temperatureScale`, with the absolute-zero probe sentinel as a fallback and
  a manual override in the options.
- Services `outlet_on`, `outlet_off`, `outlet_cycle` (all with a PDU-side
  delay) and `dump_oids`.
- Diagnostics download containing the parsed model and the complete raw walk.
- Option to expose unmapped MIB columns as diagnostic sensors.
- `tools/epdu_dump.py`, a standalone SNMP dump and verification tool.

[1.0.0]: https://github.com/nickgardner05/ha-eaton-epdu/releases/tag/v1.0.0
