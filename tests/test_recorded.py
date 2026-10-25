"""The recorded formatter output (used where mkfs does not exist) must be
what the real formatter writes."""

import pytest

from factory import exfat_image as X
from factory import fat32_image as F
from factory import recorded

BOOT_REGIONS = 24 * 512             # main and backup boot regions: volume serial, checksum


def differing(a, b, skip=0):
    x, y = open(a, "rb").read(), open(b, "rb").read()
    assert len(x) == len(y)
    return [i for i in range(skip, len(x), 512) if x[i:i + 512] != y[i:i + 512]]


@pytest.mark.parametrize("size, cluster", [(64, "4K"), (64, "32K"), (16, "4K")])
def test_replayed_exfat_is_what_mkfs_writes(tmp_path, size, cluster):
    if not X.MKFS:
        pytest.skip("mkfs.exfat is not installed here")
    real, replayed = tmp_path / "real.img", tmp_path / "replayed.img"
    open(real, "wb").truncate(size << 20)
    X.real_mkfs(real, cluster)
    recorded.replay(recorded.name_of("exfat", size, cluster), replayed, size)
    assert differing(real, replayed, BOOT_REGIONS) == []
    assert X.fsck(replayed) in (None, 0)


def test_replayed_fat32_is_what_mkfs_writes(tmp_path):
    if not F.MKFS:
        pytest.skip("mkfs.vfat is not installed here")
    real, replayed = tmp_path / "real.img", tmp_path / "replayed.img"
    open(real, "wb").truncate(64 << 20)
    F.real_mkfs(real)
    recorded.replay(recorded.name_of("fat32", 64), replayed, 64)
    # only the volume serial differs, in the boot sector and its backup
    assert differing(real, replayed) == [0, 6 * 512]
