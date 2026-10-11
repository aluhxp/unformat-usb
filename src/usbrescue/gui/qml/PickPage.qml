import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Item {
    Column {
        anchors.fill: parent
        anchors.margins: 36
        anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 18

        Txt { text: qsTr("Tranquilo, vamos a buscar tus archivos."); font.pixelSize: 32; font.weight: Font.ExtraBold; width: parent.width }
        Txt {
            text: qsTr("Elige el pendrive o la tarjeta. Solo lo vamos a leer: no se escribe nada en él.")
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
                                + (row.modelData.transport === "image" ? qsTr("copia de disco") : row.modelData.transport.toUpperCase())
                                + (row.modelData.fs ? " · " + qsTr("formato actual: %1").arg(row.modelData.fs) : "")
                        }
                    }
                }
                Rectangle {
                    visible: !row.modelData.readable
                    anchors.right: parent.right; anchors.rightMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.warnBg; radius: 11; height: 24; width: tag.implicitWidth + 18
                    Txt { id: tag; anchors.centerIn: parent; text: qsTr("Te pedirá la contraseña"); color: Theme.warnInk; font.pixelSize: 13; font.weight: Font.ExtraBold }
                }
            }
        }

        Txt {
            visible: backend.devices.length === 0
            width: parent.width
            color: Theme.soft
            text: qsTr("No vemos ningún pendrive conectado. Conéctalo y pulsa Actualizar.")
        }

        Row {
            spacing: 12
            Btn { label: qsTr("Actualizar"); primary: false; implicitHeight: 44; onClicked: backend.refreshDevices() }
            Btn { label: qsTr("Abrir una copia de disco…"); primary: false; implicitHeight: 44; onClicked: imageDialog.open() }
        }
    }

    Txt {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 36; anchors.leftMargin: 72; anchors.rightMargin: 72
        color: Theme.soft; font.pixelSize: 15
        text: qsTr("El disco de tu computadora no aparece aquí, para que no haya accidentes. Mientras tanto, no guardes nada nuevo en el pendrive: cada archivo nuevo puede tapar uno viejo.")
    }

    FileDialog {
        id: imageDialog
        title: qsTr("Elige la copia de disco")
        nameFilters: [qsTr("Copias de disco (*.img *.dd *.bin *.raw)"), qsTr("Todos los archivos (*)")]
        onAccepted: backend.addImage(selectedFile)
    }
}
