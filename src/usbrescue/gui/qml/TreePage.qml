import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Item {
    id: page
    readonly property var st: win.st
    readonly property bool scanning: st.phase === "scanning"
    property string destination: backend.defaultDestination

    Column {
        id: top
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 20; anchors.leftMargin: 32; anchors.rightMargin: 32
        spacing: 10
        Item {
            width: parent.width; height: title.implicitHeight
            Txt {
                id: title
                width: parent.width - 290
                font.pixelSize: 23; font.weight: Font.ExtraBold
                text: page.st.foundFolders === 0
                    ? qsTr("Looking for your folders…")
                    : page.scanning && page.st.rescuedEarly > 0
                    ? qsTr("%1 files rescued already; still searching").arg(win.num(page.st.rescuedEarly))
                    : (page.scanning ? qsTr("%1 files in %2 folders found so far") : qsTr("We found %1 files in %2 folders"))
                        .arg(win.num(page.st.foundFiles)).arg(win.num(page.st.foundFolders))
            }
            Txt {
                anchors.right: parent.right; anchors.baseline: title.baseline
                color: Theme.soft; font.pixelSize: 15
                text: page.scanning && page.st.scanProgress >= 1
                    ? qsTr("Sorting out what we found…")
                    : page.scanning
                    ? qsTr("Searching: %1 % · %2").arg(Math.floor(page.st.scanProgress * 100)).arg(win.eta(page.st.scanEta))
                    : qsTr("Search finished · %1").arg(backend.size(page.st.foundBytes))
            }
        }
        Bar { width: parent.width; value: page.st.scanProgress }
        Txt {
            visible: page.st.imageMade
            width: parent.width; color: Theme.accent; font.pixelSize: 14; font.weight: Font.Bold
            text: qsTr("The copy is done: you can unplug the drive now. We are working on the copy.")
        }
    }

    Card {
        id: treeCard
        anchors.left: parent.left
        anchors.top: top.bottom; anchors.bottom: bottom.top
        anchors.margins: 16; anchors.leftMargin: 32
        width: Math.round((parent.width - 64 - 16) * 0.58)

        Txt {
            visible: list.count === 0
            anchors.centerIn: parent
            color: Theme.soft
            text: qsTr("Folders will show up here.")
        }

        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 8
            clip: true
            model: backend.tree
            ScrollBar.vertical: ScrollBar {}
            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 } }
            delegate: Rectangle {
                id: row
                required property int index
                required property string name
                required property int depth
                required property int totalFiles
                required property double totalSize
                required property bool checked
                required property bool expanded
                required property bool hasChildren
                required property bool lostName
                required property bool isPending
                required property bool isGroup
                required property bool rescued
                required property int nodeId
                width: list.width - 12
                height: 44
                radius: 10
                color: !isGroup && (hover.hovered || page.st.folderId === nodeId) ? Theme.rowHover : "transparent"
                border.color: Theme.accent
                border.width: !isGroup && page.st.folderId === nodeId ? 2 : 0
                HoverHandler { id: hover }
                TapHandler { enabled: !row.isGroup; onTapped: backend.selectFolder(row.index) }

                Txt {
                    visible: row.isGroup
                    anchors.verticalCenter: parent.verticalCenter; x: 8
                    color: Theme.soft; font.pixelSize: 14; font.weight: Font.ExtraBold
                    text: qsTr("Placing: folders whose place we don't know yet")
                }
                Row {
                    visible: !row.isGroup
                    anchors.verticalCenter: parent.verticalCenter
                    x: 8 + Math.max(0, row.depth) * 26
                    spacing: 10
                    Item {
                        width: 20; height: 22
                        anchors.verticalCenter: parent.verticalCenter
                        Txt {
                            visible: row.hasChildren
                            anchors.centerIn: parent
                            text: "›"; font.pixelSize: 22; font.weight: Font.Bold; color: Theme.soft
                            rotation: row.expanded ? 90 : 0
                        }
                        TapHandler { enabled: row.hasChildren; onTapped: backend.toggleExpanded(row.index) }
                    }
                    Check {
                        anchors.verticalCenter: parent.verticalCenter
                        checked: row.checked; name: row.name
                        onToggled: (value) => backend.setChecked(row.index, value)
                    }
                    FolderIcon { anchors.verticalCenter: parent.verticalCenter; faded: row.isPending || row.lostName }
                    Txt {
                        anchors.verticalCenter: parent.verticalCenter
                        text: row.name; font.weight: Font.Bold; wrapMode: Text.NoWrap
                        elide: Text.ElideRight
                        width: Math.min(implicitWidth, Math.max(60, row.width - 220 - Math.max(0, row.depth) * 26
                                                                - (row.lostName || row.rescued ? 135 : 0)))
                    }
                    Rectangle {
                        visible: row.rescued
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.rowHover; radius: 11; height: 22; width: done.implicitWidth + 16
                        Txt { id: done; anchors.centerIn: parent; text: qsTr("Rescued"); color: Theme.accent; font.pixelSize: 13; font.weight: Font.ExtraBold }
                    }
                    Rectangle {
                        visible: row.lostName
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.warnBg; radius: 11; height: 22; width: lost.implicitWidth + 16
                        Txt { id: lost; anchors.centerIn: parent; text: qsTr("Name lost"); color: Theme.warnInk; font.pixelSize: 13; font.weight: Font.ExtraBold }
                    }
                }
                Txt {
                    visible: !row.isGroup
                    anchors.right: parent.right; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.soft; font.pixelSize: 14
                    text: row.totalFiles === 1 ? qsTr("1 file") : qsTr("%1 files").arg(win.num(row.totalFiles))
                }
            }
        }
    }

    Card {
        id: side
        anchors.left: treeCard.right; anchors.right: parent.right
        anchors.top: top.bottom; anchors.bottom: bottom.top
        anchors.margins: 16; anchors.rightMargin: 32

        Txt {
            visible: page.st.folderId < 0
            anchors.centerIn: parent
            width: parent.width - 48
            horizontalAlignment: Text.AlignHCenter
            color: Theme.soft
            text: qsTr("Pick a folder to see what is inside.")
        }

        Column {
            visible: page.st.folderId >= 0
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            Rectangle {
                id: previewBox
                visible: page.st.preview.name !== undefined
                width: parent.width
                height: visible ? 170 : 0
                radius: 10
                color: Theme.bg
                clip: true
                Image {
                    id: picture
                    visible: page.st.preview.kind === "image" && status === Image.Ready
                    anchors.fill: parent; anchors.margins: 6
                    fillMode: Image.PreserveAspectFit
                    // decoded on the UI thread, at a size that keeps it quick; the
                    // bytes were already read from the drive on a worker thread
                    sourceSize.width: 900
                    cache: false
                    source: page.st.preview.kind === "image" ? (page.st.preview.source || "") : ""
                }
                Txt {
                    visible: page.st.preview.kind === "text"
                    anchors.fill: parent; anchors.margins: 10
                    font.pixelSize: 13; font.family: "monospace"
                    wrapMode: Text.WrapAnywhere; elide: Text.ElideRight
                    text: page.st.preview.text || ""
                }
                Txt {
                    visible: page.st.preview.kind === "info" || (page.st.preview.kind === "image" && picture.status !== Image.Ready)
                    anchors.centerIn: parent
                    width: parent.width - 24; horizontalAlignment: Text.AlignHCenter
                    color: Theme.soft; font.pixelSize: 14
                    text: page.st.preview.kind === "image"
                        ? (picture.status === Image.Error ? qsTr("This picture cannot be shown: it may be damaged.") : qsTr("Loading the picture…"))
                        : qsTr("No preview for this kind of file yet.")
                }
            }
            Txt {
                visible: previewBox.visible
                width: parent.width; font.pixelSize: 14; color: Theme.soft
                elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                text: (page.st.preview.name || "") + " · " + (page.st.preview.size || "") + (page.st.preview.date ? " · " + page.st.preview.date : "")
            }
            Txt {
                width: parent.width; font.weight: Font.ExtraBold
                elide: Text.ElideRight; wrapMode: Text.NoWrap
                text: page.st.folderName
            }
            Txt {
                visible: page.st.files.length === 0
                width: parent.width; color: Theme.soft; font.pixelSize: 14
                text: qsTr("This folder has no files of its own: look inside its subfolders.")
            }
            ListView {
                id: fileList
                width: parent.width
                height: parent.height - y
                clip: true
                model: page.st.files
                ScrollBar.vertical: ScrollBar {}
                footer: Txt {
                    visible: page.st.filesHidden > 0
                    height: visible ? implicitHeight + 12 : 0
                    color: Theme.soft; font.pixelSize: 13
                    text: qsTr("…and %1 more files in this folder").arg(win.num(page.st.filesHidden))
                }
                delegate: Rectangle {
                    id: fileRow
                    required property var modelData
                    required property int index
                    width: fileList.width - 10
                    height: 38
                    radius: 8
                    color: fileHover.hovered || page.st.preview.name === modelData.name ? Theme.rowHover : "transparent"
                    HoverHandler { id: fileHover }
                    TapHandler { onTapped: backend.selectFile(fileRow.index) }
                    Check {
                        id: fileCheck
                        x: 6; anchors.verticalCenter: parent.verticalCenter
                        width: 20; height: 20
                        checked: fileRow.modelData.checked; name: fileRow.modelData.name
                        onToggled: (value) => backend.setFileChecked(fileRow.index, value)
                    }
                    Txt {
                        anchors.left: fileCheck.right; anchors.leftMargin: 10
                        anchors.right: fileSize.left; anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        font.pixelSize: 14; elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                        text: fileRow.modelData.name
                    }
                    Txt {
                        id: fileSize
                        anchors.right: parent.right; anchors.rightMargin: 6
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.soft; font.pixelSize: 13
                        text: fileRow.modelData.size
                    }
                }
            }
        }
    }

    Item {
        id: bottom
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 20; anchors.leftMargin: 32; anchors.rightMargin: 32
        height: 112

        Column {
            anchors.left: parent.left; anchors.right: go.left; anchors.rightMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Row {
                spacing: 10
                Check {
                    checked: page.st.mediaOnly
                    name: qsTr("Only photos and videos")
                    onToggled: (value) => backend.setMediaOnly(value)
                }
                Txt {
                    font.pixelSize: 15
                    text: qsTr("Only photos and videos, each in its folder")
                }
            }
            Row {
                visible: !page.scanning && page.st.orphanCount > 0
                spacing: 10
                Check {
                    checked: page.st.withOrphans
                    name: qsTr("Include files without a folder")
                    onToggled: (value) => backend.setWithOrphans(value)
                }
                Txt {
                    font.pixelSize: 15
                    readonly property int n: page.st.mediaOnly ? page.st.mediaOrphans : page.st.orphanCount
                    text: page.st.mediaOnly
                        ? qsTr("Include %1 photos and videos without a folder").arg(win.num(n))
                        : n === 1
                        ? qsTr("Include 1 file without a folder (it was loose, outside the folders)")
                        : qsTr("Include %1 files without a folder (the loose ones, outside the folders)").arg(win.num(n))
                }
            }
            Row {
                spacing: 10
                Txt {
                    color: Theme.soft; font.pixelSize: 15
                    width: Math.min(implicitWidth, bottom.width - go.width - 150)
                    elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                    text: qsTr("Will be saved in: %1").arg(page.destination)
                }
                Txt {
                    text: qsTr("Change…"); color: Theme.accent; font.pixelSize: 15; font.weight: Font.Bold
                    TapHandler { onTapped: folderDialog.open() }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
            }
        }
        Btn {
            id: go
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            enabledLook: page.scanning ? page.st.canRescueNow
                : page.st.selectedFiles + (page.st.withOrphans ? (page.st.mediaOnly ? page.st.mediaOrphans : page.st.orphanCount) : 0) > 0
            label: (page.scanning ? qsTr("Rescue the ticked ones now (%1)") : qsTr("Rescue the ticked ones (%1)")).arg(backend.size(page.st.selectedBytes))
            onClicked: backend.recover(page.destination)
        }
    }

    FolderDialog {
        id: folderDialog
        title: qsTr("Where should we save what we rescue?")
        onAccepted: page.destination = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }
}
