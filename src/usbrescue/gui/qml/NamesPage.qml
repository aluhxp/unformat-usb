import QtQuick
import QtQuick.Controls.Basic

// Proposed names for the folders that lost theirs. Nothing changes until
// the person presses the button, and it can be undone afterwards.
Item {
    id: page
    readonly property var st: win.st
    // names as typed here, by row; the rest keep the proposal
    property var edits: ({})
    readonly property int ticked: st.names.filter(r => r.checked).length

    function nameAt(i) { return edits[i] !== undefined ? edits[i] : st.names[i].name }

    Column {
        id: top
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 24; anchors.leftMargin: 40; anchors.rightMargin: 40
        spacing: 6
        Txt {
            width: parent.width; font.pixelSize: 26; font.weight: Font.ExtraBold
            text: qsTr("Names for the folders that lost theirs")
        }
        Txt {
            width: parent.width; color: Theme.soft; font.pixelSize: 15
            text: page.st.namesBusy
                ? qsTr("Looking at what each folder holds…")
                : qsTr("When we find the original name inside some file, we use it. Otherwise we suggest one from what the folder holds. You can change it before applying it.")
        }
    }

    Card {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: top.bottom; anchors.bottom: bottom.top
        anchors.margins: 16; anchors.leftMargin: 40; anchors.rightMargin: 40

        Txt {
            visible: !page.st.namesBusy && list.count === 0
            anchors.centerIn: parent; color: Theme.soft
            text: qsTr("No folders without a name are left.")
        }
        ListView {
            id: list
            anchors.fill: parent; anchors.margins: 10
            clip: true; spacing: 4
            model: page.st.names
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                width: list.width - 12; height: 76; radius: 10
                color: hover.hovered ? Theme.rowHover : "transparent"
                HoverHandler { id: hover }

                Check {
                    id: tick
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    checked: row.modelData.checked; name: row.modelData.current
                    onToggled: (value) => backend.setNameChecked(row.index, value)
                }
                Column {
                    anchors.left: tick.right; anchors.leftMargin: 16
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Row {
                        spacing: 10; width: parent.width
                        TextField {
                            id: field
                            width: Math.min(360, parent.width - tag.width - 10)
                            height: 36
                            text: page.nameAt(row.index)
                            enabled: row.modelData.checked
                            font.family: Theme.family; font.pixelSize: 16; font.weight: Font.Bold
                            color: Theme.ink
                            selectByMouse: true
                            Accessible.name: qsTr("New name for %1").arg(row.modelData.current)
                            background: Rectangle {
                                radius: 8; color: Theme.bg
                                border.color: field.activeFocus ? Theme.accent : Theme.line
                                border.width: field.activeFocus ? 2 : 1
                            }
                            onTextEdited: {
                                const e = Object.assign({}, page.edits)
                                e[row.index] = text
                                page.edits = e
                            }
                        }
                        Rectangle {
                            id: tag
                            anchors.verticalCenter: parent.verticalCenter
                            height: 24; radius: 12
                            width: tagText.implicitWidth + 18
                            color: row.modelData.source === "original" ? Theme.rowHover : Theme.warnBg
                            Txt {
                                id: tagText; anchors.centerIn: parent
                                font.pixelSize: 13; font.weight: Font.ExtraBold
                                color: row.modelData.source === "original" ? Theme.accent : Theme.warnInk
                                text: row.modelData.source === "original" ? qsTr("Original name") : qsTr("Suggested from content")
                            }
                        }
                    }
                    Txt {
                        readonly property string count: row.modelData.files === 1 ? qsTr("1 file") : qsTr("%1 files").arg(win.num(row.modelData.files))
                        width: parent.width; color: Theme.soft; font.pixelSize: 13
                        wrapMode: Text.NoWrap; elide: Text.ElideMiddle
                        text: row.modelData.source === "original"
                            ? qsTr("Now: %1 · %2 · seen in %3").arg(row.modelData.current).arg(count).arg(row.modelData.example)
                            : qsTr("Now: %1 · %2").arg(row.modelData.current).arg(count)
                    }
                }
            }
        }
    }

    Row {
        id: bottom
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.margins: 24; anchors.leftMargin: 40
        spacing: 14
        Btn {
            label: qsTr("Rename the ticked ones (%1)").arg(page.ticked)
            enabledLook: !page.st.namesBusy && page.ticked > 0
            onClicked: backend.applyNames(page.st.names.map((r, i) => page.nameAt(i)))
        }
        Btn { label: qsTr("Go back without changes"); primary: false; onClicked: backend.closeNames() }
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            visible: page.st.namesError !== ""
            color: Theme.warn; font.pixelSize: 14; font.weight: Font.Bold
            text: page.st.namesError === "twice" ? qsTr("Two folders cannot have the same name.")
                : page.st.namesError.startsWith("exists:") ? qsTr("There is already a folder called “%1”. Choose another name.").arg(page.st.namesError.slice(7))
                : qsTr("Could not rename: %1").arg(page.st.namesError.slice(3))
        }
    }
}
