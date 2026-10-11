import QtQuick

Item {
    id: page
    readonly property var st: win.st

    Column {
        anchors.fill: parent
        anchors.margins: 30; anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 22

        Row {
            spacing: 22; width: parent.width
            Mascot { width: 84; mood: "happy" }
            Column {
                width: parent.width - 106; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Txt {
                    width: parent.width; font.pixelSize: 32; font.weight: Font.ExtraBold
                    text: qsTr("¡Listo! Rescatamos %1 archivos.").arg(win.num(page.st.sumOk + page.st.sumWarned + page.st.sumOrphans))
                }
                Txt { width: parent.width; color: Theme.soft; elide: Text.ElideMiddle; wrapMode: Text.NoWrap; text: qsTr("Están en %1").arg(page.st.destPath) }
            }
        }

        Row {
            width: parent.width; spacing: 14
            Repeater {
                model: [
                    { n: page.st.sumOk, label: qsTr("salieron bien"), tone: Theme.accent },
                    { n: page.st.sumWarned, label: qsTr("conviene revisar"), tone: page.st.sumWarned ? Theme.warn : Theme.ink },
                    { n: page.st.sumOrphans, label: qsTr("sueltos, sin carpeta"), tone: Theme.ink },
                    { n: page.st.sumUnnamed, label: qsTr("carpetas sin su nombre"), tone: page.st.sumUnnamed ? Theme.warn : Theme.ink }
                ]
                Card {
                    required property var modelData
                    width: (parent.width - 42) / 4; height: 92
                    Column {
                        anchors.fill: parent; anchors.margins: 14; spacing: 2
                        Txt { text: win.num(parent.parent.modelData.n); color: parent.parent.modelData.tone; font.pixelSize: 28; font.weight: Font.ExtraBold }
                        Txt { width: parent.width; text: parent.parent.modelData.label; font.pixelSize: 14; font.weight: Font.Bold }
                    }
                }
            }
        }

        Row {
            spacing: 14
            Btn { label: qsTr("Abrir la carpeta"); onClicked: backend.openDestination() }
            Btn { label: qsTr("Ver el informe"); primary: false; onClicked: backend.openReport() }
            Btn { label: qsTr("Rescatar otro pendrive"); primary: false; onClicked: backend.back() }
        }

        Txt {
            width: parent.width; color: Theme.soft; font.pixelSize: 15
            text: qsTr("Abre algunos archivos importantes para comprobar que están bien antes de volver a usar el pendrive. El informe dice cuáles conviene revisar.")
        }
    }
}
