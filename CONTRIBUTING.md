# Contributing

Thank you for helping. A few rules keep Unformat USB safe for the people who need it:

1. **Never write to the source.** Every read of a drive goes through `core/reader.py`, which opens
   it read-only. No change may weaken that.
2. **Never use real people's data in tests.** Test drives are built from scratch by `tests/factory/`.
3. **Be honest with users.** If something cannot be recovered, the program says so.
4. **Plain words** in the window, in English, Spanish and Portuguese.

## Getting started

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,gui]"
.venv/bin/python -m pytest -q
```

- New screen text: write it in English with `qsTr("…")`, run `python tools/i18n.py`, and translate
  it in `src/usbrescue/gui/i18n/es.ts` and `pt.ts` (`pyside6-linguist` opens them). The tests fail
  while a text has no translation.
- Words the program writes to disk (folder names, the report) live in `src/usbrescue/texts.py`.
- The web page is built by `tools/build_site.py` into `docs/`.
- Screenshots: `python tools/screens.py OUT [--dark] [--es|--pt]`.

Small commits with clear messages, please. By contributing you agree that your work is licensed
under the [GPL-3.0-or-later](LICENSE).
