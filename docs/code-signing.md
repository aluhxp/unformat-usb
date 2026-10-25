# Code signing policy

Windows builds of Unformat USB are meant to be signed through the
[SignPath Foundation](https://signpath.org) free code signing program for open source projects
(free code signing provided by [SignPath.io](https://signpath.io), certificate by SignPath Foundation).
Until the project is approved, releases are unsigned.

## What gets signed

Only `UnformatUSB.exe`, built by the public [build workflow](../.github/workflows/build.yml) from
this repository's source on GitHub Actions. Nothing built on a personal computer is ever signed.
Release signing happens only for version tags (`v*`), after the program has passed its automatic
checks on a disk image and on a whole disk.

## Team roles

- Committers and reviewers: [aluhxp](https://github.com/aluhxp)
- Approvers: [aluhxp](https://github.com/aluhxp)

Every release signing request is approved by hand.

## Privacy

This program does not send any information to other computers or networks. It only reads the drive
the user chooses and writes the rescued files to the folder the user chooses. The single exception
happens when the user presses **Donate**: the program then opens PayPal's donation page in the web browser.
