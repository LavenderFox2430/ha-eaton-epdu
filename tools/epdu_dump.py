#!/usr/bin/env python3
"""Walk an Eaton ePDU and print/save everything it exposes.

Standalone: needs only `pip install pysnmp`, no Home Assistant. Use it to
check credentials before adding the integration, and to confirm the column
map in `custom_components/eaton_epdu/oids.py` against your own firmware.

Examples:
    python epdu_dump.py 192.168.1.96 --v3 --user HomeAssistant --auth-key SECRET
    python epdu_dump.py 192.168.1.96 --v3 --user ha --auth-proto sha \
        --auth-key SECRET --priv-proto aes128 --priv-key SECRET2
    python epdu_dump.py 192.168.1.96 --v1 --community public
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pyasn1.type import univ
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
    usm3DESEDEPrivProtocol,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC128SHA224AuthProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC256SHA384AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
    walk_cmd,
)
from pysnmp.proto import rfc1902, rfc1905

BASE = "1.3.6.1.4.1.534.6.6.7"

AUTH = {
    "none": usmNoAuthProtocol,
    "md5": usmHMACMD5AuthProtocol,
    "sha": usmHMACSHAAuthProtocol,
    "sha224": usmHMAC128SHA224AuthProtocol,
    "sha256": usmHMAC192SHA256AuthProtocol,
    "sha384": usmHMAC256SHA384AuthProtocol,
    "sha512": usmHMAC384SHA512AuthProtocol,
}
PRIV = {
    "none": usmNoPrivProtocol,
    "des": usmDESPrivProtocol,
    "3des": usm3DESEDEPrivProtocol,
    "aes128": usmAesCfb128Protocol,
    "aes192": usmAesCfb192Protocol,
    "aes256": usmAesCfb256Protocol,
}

SYS_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
}

#: Table entry OID (relative to BASE) -> human name, for the printed report.
TABLE_NAMES = {
    "1.2.1": "unitTable",
    "1.3.1": "unitControlTable?",
    "3.1.1": "inputTable",
    "3.2.1": "inputVoltageTable",
    "3.3.1": "inputCurrentTable",
    "3.4.1": "inputPowerTable",
    "3.5.1": "inputTotalPowerTable",
    "5.1.1": "groupTable",
    "5.2.1": "groupChildTable",
    "5.3.1": "groupVoltageTable",
    "5.4.1": "groupCurrentTable",
    "5.5.1": "groupPowerTable",
    "5.6.1": "groupControlTable",
    "6.1.1": "outletTable",
    "6.2.1": "outletChildTable",
    "6.3.1": "outletVoltageTable",
    "6.4.1": "outletCurrentTable",
    "6.5.1": "outletPowerTable",
    "6.6.1": "outletControlTable",
    "7.1.1": "temperatureTable",
    "7.2.1": "humidityTable",
    "7.3.1": "contactTable",
}


def to_python(value: Any) -> Any:
    """Convert a pysnmp value to something JSON can hold."""
    if value is None:
        return None
    if isinstance(value, (rfc1905.NoSuchObject, rfc1905.NoSuchInstance, rfc1905.EndOfMibView)):
        return None
    if isinstance(value, univ.Null):
        return None
    if isinstance(value, rfc1902.IpAddress):
        return value.prettyPrint()
    if isinstance(value, univ.Integer):
        return int(value)
    if isinstance(value, univ.OctetString):
        octets = value.asOctets()
        try:
            return octets.decode("utf-8").replace("\x00", "").strip()
        except UnicodeDecodeError:
            return "0x" + octets.hex()
    if isinstance(value, univ.ObjectIdentifier):
        return str(value)
    return value.prettyPrint()


def oid_string(name: Any) -> str:
    """Return a dotted OID string."""
    try:
        return ".".join(str(part) for part in name.getOid().asTuple())
    except Exception:  # noqa: BLE001
        return str(name).strip(". ")


def auth_data(args: argparse.Namespace) -> CommunityData | UsmUserData:
    """Build pysnmp credentials from the command line."""
    if args.version == "v3":
        return UsmUserData(
            args.user,
            authKey=args.auth_key or None,
            privKey=args.priv_key or None,
            authProtocol=AUTH[args.auth_proto],
            privProtocol=PRIV[args.priv_proto],
        )
    return CommunityData(args.community, mpModel=0 if args.version == "v1" else 1)


async def run(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    """Walk the PDU, print the report and fill `payload` with the raw result."""
    engine = SnmpEngine()
    credentials = auth_data(args)
    context = ContextData()

    try:
        target = await UdpTransportTarget.create(
            (args.host, args.port), timeout=args.timeout, retries=args.retries
        )

        system: dict[str, Any] = {}
        for label, oid in SYS_OIDS.items():
            indication, status, _, var_binds = await get_cmd(
                engine,
                credentials,
                target,
                context,
                ObjectType(ObjectIdentity(oid)),
                lookupMib=False,
            )
            if indication:
                print(f"ERROR: {indication}", file=sys.stderr)
                if "digest" in str(indication).lower() or "usm" in str(indication).lower():
                    print(
                        "Hint: the PDU rejected the credentials. Check the user "
                        "name, the auth protocol (G3 usually uses SHA) and the "
                        "password.",
                        file=sys.stderr,
                    )
                return 2
            system[label] = None if status else to_python(var_binds[0][1])

        print("=== SYSTEM ===")
        for label, value in system.items():
            print(f"  {label:<12} {value}")

        walker = (
            walk_cmd(
                engine,
                credentials,
                target,
                context,
                ObjectType(ObjectIdentity(BASE)),
                lexicographicMode=False,
                lookupMib=False,
                maxRows=20000,
            )
            if args.version == "v1"
            else bulk_walk_cmd(
                engine,
                credentials,
                target,
                context,
                0,
                args.max_repetitions,
                ObjectType(ObjectIdentity(BASE)),
                lexicographicMode=False,
                lookupMib=False,
                maxRows=20000,
            )
        )

        data: dict[str, Any] = {}
        async for indication, status, index, var_binds in walker:
            if indication:
                print(f"ERROR during walk: {indication}", file=sys.stderr)
                break
            if status:
                print(f"ERROR during walk: {status.prettyPrint()} at {index}", file=sys.stderr)
                break
            for name, value in var_binds:
                oid = oid_string(name)
                if oid == BASE or oid.startswith(f"{BASE}."):
                    data[oid] = to_python(value)
    finally:
        engine.close_dispatcher()

    if not data:
        print(
            f"\nNo data under {BASE}. The device answered but exposes no Eaton "
            "ePDU MIB, or the SNMP user has no read access to it.",
            file=sys.stderr,
        )
        return 3

    report(data)

    payload.update({"host": args.host, "system": system, "eaton": dict(sorted(data.items()))})
    return 0


def report(data: dict[str, Any]) -> None:
    """Print the walk grouped into tables, columns and rows."""
    tables: dict[str, dict[int, dict[tuple[int, ...], Any]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    scalars: dict[str, Any] = {}

    for oid, value in sorted(data.items(), key=lambda kv: [int(p) for p in kv[0].split(".")]):
        parts = [int(p) for p in oid[len(BASE) + 1 :].split(".")]
        if len(parts) >= 4:
            entry = ".".join(str(p) for p in parts[:3])
            tables[entry][parts[3]][tuple(parts[4:])] = value
        else:
            scalars[oid] = value

    if scalars:
        print("\n=== SCALARS ===")
        for oid, value in scalars.items():
            suffix = oid[len(BASE) + 1 :]
            note = " (unitsPresent)" if suffix == "1.1.0" else ""
            print(f"  {oid} = {value!r}{note}")

    for entry, columns in tables.items():
        rows = {index for column in columns.values() for index in column}
        name = TABLE_NAMES.get(entry, "unknown table")
        print(f"\n=== {BASE}.{entry}  {name}  ({len(rows)} rows) ===")
        print(f"    indexes: {sorted(rows)[:10]}{' ...' if len(rows) > 10 else ''}")
        for number in sorted(columns):
            sample = list(columns[number].items())[:4]
            rendered = ", ".join(f"{index}={value!r}" for index, value in sample)
            print(f"    col {number:>2}: {rendered}")


def main() -> int:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=161)
    version = parser.add_mutually_exclusive_group()
    version.add_argument("--v1", dest="version", action="store_const", const="v1")
    version.add_argument("--v2c", dest="version", action="store_const", const="v2c")
    version.add_argument("--v3", dest="version", action="store_const", const="v3")
    parser.add_argument("--community", default="public")
    parser.add_argument("--user", default="")
    parser.add_argument("--auth-proto", choices=sorted(AUTH), default="sha")
    parser.add_argument("--auth-key", default="")
    parser.add_argument("--priv-proto", choices=sorted(PRIV), default="none")
    parser.add_argument("--priv-key", default="")
    parser.add_argument("--timeout", type=int, default=5)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-repetitions", type=int, default=25)
    parser.add_argument("--output", default="epdu_dump.json")
    parser.set_defaults(version="v3")
    args = parser.parse_args()

    if args.version == "v3" and not args.user:
        parser.error("--user is required for SNMPv3")

    payload: dict[str, Any] = {}
    code = asyncio.run(run(args, payload))
    if payload:
        Path(args.output).write_text(
            json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8"
        )
        print(f"\n{len(payload['eaton'])} OIDs written to {args.output}")
    return code


if __name__ == "__main__":
    sys.exit(main())
