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
            text: qsTr("Nombres para las carpetas que perdieron el suyo")
        }
        Txt {
            width: parent.width; color: Theme.soft; font.pixelSize: 15
            text: page.st.namesBusy
                ? qsTr("Mirando lo que hay dentro de cada carpeta…")
                : qsTr("Cuando encontramos el nombre original dentro de algún archivo, lo usamos. Si no, proponemos uno según lo que contiene. Puedes cambiarlo antes de aplicarlo.")
        }
    }

    Card {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: top.bottom; anchors.bottom: bottom.top
        anchors.margins: 16; anchors.leftMargin: 40; anchors.rightMargin: 40

        Txt {
            visible: !page.st.namesBusy && list.count === 0
            anchors.centerIn: parent; color: Theme.soft
            text: qsTr("No quedan carpetas sin nombre.")
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
                            Accessible.name: qsTr("Nuevo nombre para %1").arg(row.modelData.current)
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
                                text: row.modelData.source === "original" ? qsTr("Nombre original") : qsTr("Sugerido por el contenido")
                            }
                        }
                    }
                    Txt {
                        readonly property string count: row.modelData.files === 1 ? qsTr("1 archivo") : qsTr("%1 archivos").arg(win.num(row.modelData.files))
                        width: parent.width; color: Theme.soft; font.pixelSize: 13
                        wrapMode: Text.NoWrap; elide: Text.ElideMiddle
                        text: row.modelData.source === "original"
                            ? qsTr("Ahora: %1 · %2 · lo vimos en %3").arg(row.modelData.current).arg(count).arg(row.modelData.example)
                            : qsTr("Ahora: %1 · %2").arg(row.modelData.current).arg(count)
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
            label: qsTr("Renombrar las marcadas (%1)").arg(page.ticked)
            enabledLook: !page.st.namesBusy && page.ticked > 0
            onClicked: backend.applyNames(page.st.names.map((r, i) => page.nameAt(i)))
        }
        Btn { label: qsTr("Volver sin cambiar nada"); primary: false; onClicked: backend.closeNames() }
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            visible: page.st.namesError !== ""
            color: Theme.warn; font.pixelSize: 14; font.weight: Font.Bold
            text: page.st.namesError === "twice" ? qsTr("Dos carpetas no pueden llamarse igual.")
                : page.st.namesError.startsWith("exists:") ? qsTr("Ya hay una carpeta llamada «%1». Elige otro nombre.").arg(page.st.namesError.slice(7))
                : qsTr("No se pudo renombrar: %1").arg(page.st.namesError.slice(3))
        }
    }
}
