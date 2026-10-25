# winget

Manifests for `winget install aluhxp.UnformatUSB`. To send a version to
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) from Windows:

```
winget install wingetcreate
wingetcreate submit packaging\winget\0.1.1
```

For a new version: `wingetcreate update aluhxp.UnformatUSB --version X.Y.Z --urls <exe url> --submit`.
