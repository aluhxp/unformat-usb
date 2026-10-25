import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Item {
    Column {
        anchors.fill: parent
        anchors.margins: 36
        anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 18

        Txt { text: qsTr("Don't worry, let's find your files."); font.pixelSize: 32; font.weight: Font.ExtraBold; width: parent.width }
        Txt {
            text: qsTr("Choose the drive or card. We will only read it: nothing is written to it.")
            color: Theme.soft; font.pixelSize: 17; width: parent.width
        }

        ListView {
            id: list
            width: parent.width
            height: Math.min(contentHeight, 250)
            spacing: 12
            clip: true
            model: backend.devices
            ScrollBar.vertical: ScrollBar {}
            delegate: Card {
                id: row
                required property var modelData
                required property int index
                width: list.width
                height: 76
                border.width: 2
                border.color: hover.hovered || activeFocus ? Theme.accent : Theme.line
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.name
                Keys.onReturnPressed: backend.choose(index)
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: backend.choose(row.index) }
                Row {
                    anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20
                    spacing: 16
                    Mascot { width: 34; anchors.verticalCenter: parent.verticalCenter }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Txt { text: row.modelData.name; font.pixelSize: 18; font.weight: Font.ExtraBold }
                        Txt {
                            color: Theme.soft; font.pixelSize: 15
                            text: row.modelData.size + " · "
                                + (row.modelData.transport === "image" ? qsTr("disk image") : row.modelData.transport.toUpperCase())
                                + (row.modelData.fs ? " · " + qsTr("current format: %1").arg(row.modelData.fs) : "")
                        }
                    }
                }
                Rectangle {
                    visible: !row.modelData.readable
                    anchors.right: parent.right; anchors.rightMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.warnBg; radius: 11; height: 24; width: tag.implicitWidth + 18
                    Txt { id: tag; anchors.centerIn: parent; text: qsTr("Will ask for your password"); color: Theme.warnInk; font.pixelSize: 13; font.weight: Font.ExtraBold }
                }
            }
        }

        Txt {
            visible: backend.devices.length === 0
            width: parent.width
            color: Theme.soft
            text: qsTr("We don't see any drive plugged in. Plug it in and press Refresh.")
        }

        Row {
            spacing: 12
            Btn { label: qsTr("Refresh"); primary: false; implicitHeight: 44; onClicked: backend.refreshDevices() }
            Btn { label: qsTr("Open a disk image…"); primary: false; implicitHeight: 44; onClicked: imageDialog.open() }
        }
    }

    Txt {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 36; anchors.leftMargin: 72; anchors.rightMargin: 72
        color: Theme.soft; font.pixelSize: 15
        text: qsTr("Your computer's own disk is not listed, to avoid accidents. Meanwhile, don't save anything new on the drive: every new file can cover an old one.")
    }

    FileDialog {
        id: imageDialog
        title: qsTr("Choose the disk image")
        nameFilters: [qsTr("Disk images (*.img *.dd *.bin *.raw)"), qsTr("All files (*)")]
        onAccepted: backend.addImage(selectedFile)
    }
}
