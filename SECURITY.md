# Security

Unformat USB reads whole drives with administrator rights, so security problems matter a lot.

**Please report them privately**, through [a security advisory](https://github.com/aluhxp/unformat-usb/security/advisories/new),
not in a public issue. You will get an answer within a week.

Things we especially want to hear about:

- any way the program could write to the drive it rescues from;
- any way the privileged drive reader (`src/usbrescue/helper.py`) could be made to read something
  other than a removable drive, or to do anything besides reading;
- a downloaded program whose checksum does not match the one built by the
  [build workflow](.github/workflows/build.yml).

Only the latest version is supported.
