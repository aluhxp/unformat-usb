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


# ------------------------------------------------------------ Windows, macOS

def test_windows_lists_usb_and_sd_but_never_the_system_disk():
    from usbrescue.devices.windows import parse_disks
    text = ('[{"Number":0,"Name":"Samsung SSD 980","Size":1000204886016,"Bus":"NVMe","Fs":"NTFS",'
            '"Boot":true,"System":true},'
            '{"Number":1,"Name":"Kingston DataTraveler 3.0","Size":61872793600,"Bus":"USB",'
            '"Fs":"exFAT","Boot":false,"System":false},'
            '{"Number":2,"Name":"SD Card Reader","Size":0,"Bus":"USB","Fs":null,"Boot":false,"System":false},'
            '{"Number":3,"Name":"Generic SD","Size":31914983424,"Bus":"12","Fs":"FAT32",'
            '"Boot":false,"System":false},'
            '{"Number":4,"Name":"Boot USB","Size":31914983424,"Bus":"USB","Fs":"NTFS",'
            '"Boot":true,"System":false}]')
    got = parse_disks(text, readable=True)
    assert [(d.path, d.name, d.transport, d.fs) for d in got] == [
        ("\\\\.\\PhysicalDrive1", "Kingston DataTraveler 3.0", "usb", "exfat"),
        ("\\\\.\\PhysicalDrive3", "Generic SD", "mmc", "fat32")]


def test_windows_with_a_single_disk_gives_an_object_not_a_list():
    from usbrescue.devices.windows import parse_disks
    one = '{"Number":5,"Name":"","Size":8000000000,"Bus":"7","Fs":"","Boot":false,"System":false}'
    [d] = parse_disks(one)
    assert (d.path, d.name, d.transport) == ("\\\\.\\PhysicalDrive5", "Disco 5", "usb")


def test_macos_describes_external_disks_only():
    from usbrescue.devices.macos import describe
    usb = {"DeviceIdentifier": "disk4", "WholeDisk": True, "Internal": False,
           "RemovableMediaOrExternalDevice": True, "TotalSize": 61872793600,
           "MediaName": "DataTraveler 3.0", "BusProtocol": "USB"}
    d = describe(usb, [{"Content": "Microsoft Basic Data", "FilesystemType": "exfat"}])
    assert (d.path, d.name, d.size, d.transport, d.fs) == \
        ("/dev/rdisk4", "DataTraveler 3.0", 61872793600, "usb", "exfat")
    inner = dict(usb, DeviceIdentifier="disk0", Internal=True, RemovableMediaOrExternalDevice=False)
    assert describe(inner, []) is None
