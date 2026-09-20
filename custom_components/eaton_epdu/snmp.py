"""Thin async SNMP client for the Eaton ePDU integration.

Wraps pysnmp's v3arch asyncio API. Only three operations are needed: a scalar
GET (connectivity check), a subtree walk (all data) and an integer SET (outlet
control).
"""

from __future__ import annotations

import logging
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
    set_cmd,
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

from .const import VERSION_V1, VERSION_V3

_LOGGER = logging.getLogger(__name__)

AUTH_PROTOCOL_MAP = {
    "none": usmNoAuthProtocol,
    "md5": usmHMACMD5AuthProtocol,
    "sha": usmHMACSHAAuthProtocol,
    "sha224": usmHMAC128SHA224AuthProtocol,
    "sha256": usmHMAC192SHA256AuthProtocol,
    "sha384": usmHMAC256SHA384AuthProtocol,
    "sha512": usmHMAC384SHA512AuthProtocol,
}

PRIV_PROTOCOL_MAP = {
    "none": usmNoPrivProtocol,
    "des": usmDESPrivProtocol,
    "3des": usm3DESEDEPrivProtocol,
    "aes128": usmAesCfb128Protocol,
    "aes192": usmAesCfb192Protocol,
    "aes256": usmAesCfb256Protocol,
}

#: Hard stop so a broken agent cannot walk forever.
MAX_WALK_ROWS = 20000


class SnmpError(Exception):
    """Raised when an SNMP operation fails."""


def snmp_to_python(value: Any) -> Any:
    """Convert a pysnmp value into a plain Python value."""
    if value is None:
        return None
    if isinstance(value, (rfc1905.NoSuchObject, rfc1905.NoSuchInstance, rfc1905.EndOfMibView)):
        return None
    if isinstance(value, univ.Null):
        return None
    # IpAddress subclasses OctetString, so it has to be checked first.
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


def oid_to_string(name: Any) -> str:
    """Return a dotted OID string for a pysnmp object name."""
    try:
        return ".".join(str(part) for part in name.getOid().asTuple())
    except Exception:  # noqa: BLE001 - pysnmp raises several unrelated types
        return str(name).strip(". ")


class SnmpClient:
    """Minimal SNMP client bound to one PDU."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        version: str,
        community: str | None = None,
        write_community: str | None = None,
        username: str | None = None,
        auth_protocol: str = "none",
        auth_key: str | None = None,
        priv_protocol: str = "none",
        priv_key: str | None = None,
        timeout: int = 5,
        retries: int = 2,
        max_repetitions: int = 25,
    ) -> None:
        """Store connection parameters and create the SNMP engine."""
        self.host = host
        self.port = port
        self.version = version
        self._community = community
        self._write_community = write_community or community
        self._username = username
        self._auth_protocol = auth_protocol
        self._auth_key = auth_key
        self._priv_protocol = priv_protocol
        self._priv_key = priv_key
        self._timeout = timeout
        self._retries = retries
        self._max_repetitions = max_repetitions
        self._engine = SnmpEngine()

    # -- plumbing ------------------------------------------------------------
    def _auth_data(self, write: bool = False) -> CommunityData | UsmUserData:
        if self.version == VERSION_V3:
            auth_protocol = AUTH_PROTOCOL_MAP.get(self._auth_protocol, usmNoAuthProtocol)
            priv_protocol = PRIV_PROTOCOL_MAP.get(self._priv_protocol, usmNoPrivProtocol)
            return UsmUserData(
                self._username or "",
                authKey=self._auth_key or None,
                privKey=self._priv_key or None,
                authProtocol=auth_protocol,
                privProtocol=priv_protocol,
            )
        community = self._write_community if write else self._community
        # mpModel 0 selects SNMPv1, 1 selects SNMPv2c.
        return CommunityData(community or "public", mpModel=0 if self.version == VERSION_V1 else 1)

    async def _target(self) -> UdpTransportTarget:
        try:
            return await UdpTransportTarget.create(
                (self.host, self.port), timeout=self._timeout, retries=self._retries
            )
        except Exception as err:
            raise SnmpError(f"Cannot reach {self.host}:{self.port}: {err}") from err

    @staticmethod
    def _check(error_indication: Any, error_status: Any, error_index: Any) -> None:
        if error_indication:
            raise SnmpError(str(error_indication))
        if error_status:
            raise SnmpError(f"{error_status.prettyPrint()} at index {error_index or '?'}")

    # -- operations ----------------------------------------------------------
    async def get(self, oids: list[str]) -> dict[str, Any]:
        """GET a list of scalar OIDs. Unreadable OIDs come back as None."""
        if not oids:
            return {}
        target = await self._target()
        result: dict[str, Any] = {}
        # One varbind per request keeps a single unsupported OID from failing
        # the whole batch on picky agents.
        for oid in oids:
            error_indication, error_status, _, var_binds = await get_cmd(
                self._engine,
                self._auth_data(),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lookupMib=False,
            )
            if error_indication:
                raise SnmpError(str(error_indication))
            if error_status:
                result[oid] = None
                continue
            result[oid] = snmp_to_python(var_binds[0][1]) if var_binds else None
        return result

    async def walk(self, root_oid: str) -> dict[str, Any]:
        """Walk a subtree and return {oid: value}."""
        target = await self._target()
        auth = self._auth_data()
        context = ContextData()
        var_bind = ObjectType(ObjectIdentity(root_oid))
        options = {
            "lexicographicMode": False,
            "lookupMib": False,
            "maxRows": MAX_WALK_ROWS,
            "ignoreNonIncreasingOid": False,
        }

        if self.version == VERSION_V1:
            # SNMPv1 has no GETBULK.
            generator = walk_cmd(self._engine, auth, target, context, var_bind, **options)
        else:
            generator = bulk_walk_cmd(
                self._engine, auth, target, context, 0, self._max_repetitions, var_bind, **options
            )

        result: dict[str, Any] = {}
        async for error_indication, error_status, error_index, var_binds in generator:
            self._check(error_indication, error_status, error_index)
            for name, value in var_binds:
                oid = oid_to_string(name)
                if oid == root_oid or oid.startswith(f"{root_oid}."):
                    result[oid] = snmp_to_python(value)
        return result

    async def set_integer(self, oid: str, value: int) -> None:
        """SET an Integer32 OID (outlet/group control)."""
        target = await self._target()
        error_indication, error_status, error_index, _ = await set_cmd(
            self._engine,
            self._auth_data(write=True),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid), rfc1902.Integer32(value)),
            lookupMib=False,
        )
        self._check(error_indication, error_status, error_index)
        _LOGGER.debug("SET %s = %s on %s", oid, value, self.host)

    def close(self) -> None:
        """Release the SNMP engine's transport dispatcher."""
        try:
            self._engine.close_dispatcher()
        except Exception as err:  # noqa: BLE001 - best effort teardown
            _LOGGER.debug("Error closing SNMP dispatcher: %s", err)
