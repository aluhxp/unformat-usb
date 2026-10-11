import json

from usbrescue.devices.linux import parse_lsblk

LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "size": 960197124096, "model": "KINGSTON SA400", "tran": "sata", "rm": False,
     "hotplug": False, "type": "disk", "fstype": None, "mountpoints": [None],
     "children": [{"name": "sda2", "type": "part", "fstype": "ext4", "mountpoints": ["/"]}]},
    {"name": "sdb", "size": 61872793600, "model": "DataTraveler 3.0", "tran": "usb", "rm": True,
     "hotplug": True, "type": "disk", "fstype": None, "mountpoints": [None],
     "children": [{"name": "sdb1", "type": "part", "fstype": "exfat", "mountpoints": ["/run/media/u/X"]}]},
    {"name": "sdc", "size": 0, "model": "Card Reader", "tran": "usb", "rm": True, "hotplug": True,
     "type": "disk", "fstype": None, "mountpoints": [None]},
    {"name": "sdd", "size": 500107862016, "model": "Portable SSD", "tran": "usb", "rm": False,
     "hotplug": True, "type": "disk", "fstype": None, "mountpoints": [None],
     "children": [{"name": "sdd1", "type": "part", "fstype": "ext4", "mountpoints": ["/"]}]},
    {"name": "loop1", "size": 1000, "type": "loop", "rm": False, "mountpoints": ["/snap/x"]},
]})


def test_only_removable_drives_with_something_in_them_are_offered():
    devices = parse_lsblk(LSBLK)
    assert [(d.path, d.name, d.fs) for d in devices] == [("/dev/sdb", "DataTraveler 3.0", "exfat")]


def test_a_usb_disk_the_system_runs_from_is_never_offered():
    assert "/dev/sdd" not in [d.path for d in parse_lsblk(LSBLK)]
