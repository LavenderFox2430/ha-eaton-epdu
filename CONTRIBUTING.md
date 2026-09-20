# Contributing

## Adding or correcting an OID

All hardware knowledge lives in one file:
[`custom_components/eaton_epdu/oids.py`](custom_components/eaton_epdu/oids.py).
The coordinator walks the whole `1.3.6.1.4.1.534.6.6.7` subtree and classifies
what comes back, so adding support for a value is a matter of naming a column,
never of adding a fetch.

1. Dump your unit:

   ```bash
   pip install pysnmp
   python tools/epdu_dump.py <host> --v3 --user <user> --auth-key <password>
   ```

2. Find the table entry OID and column number in the output.
3. Check the name and enumeration against the published EATON-EPDU-MIB, and
   record it in the column's `mib=` field so the mapping stays traceable.
4. Add the `Column(...)` to the right `Table` in `oids.py`.
5. Update [`docs/OID_MAP.md`](docs/OID_MAP.md) with the observed value.

A column your firmware does not return simply produces no entity, so it is
safe to map columns other models have.

## Checks

```bash
pip install ruff
ruff check .
ruff format --check .
```

CI also runs Home Assistant's `hassfest` and the HACS validation action.

## Brand images

`custom_components/eaton_epdu/brand/` holds the icons, regenerated with
`python tools/make_brand_icons.py` (needs Pillow). The artwork is original and
deliberately not the Eaton logo, which is a trademark this repository has no
licence to redistribute.
