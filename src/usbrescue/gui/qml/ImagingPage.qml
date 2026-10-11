import QtQuick

Item {
    id: page
    readonly property var st: win.st

    Column {
        anchors.fill: parent
        anchors.margins: 36; anchors.leftMargin: 110; anchors.rightMargin: 110
        spacing: 20

        Mascot { width: 72; mood: "working"; anchors.horizontalCenter: parent.horizontalCenter }
        Txt {
            width: parent.width; horizontalAlignment: Text.AlignHCenter
            text: qsTr("Copiando tu pendrive a un lugar seguro…"); font.pixelSize: 30; font.weight: Font.ExtraBold
        }
        Txt {
            width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.soft
            text: qsTr("Primero hacemos una copia completa en tu computadora. Así, si el pendrive falla, no se pierde nada. Después buscamos tus archivos en la copia.")
        }
        Bar { width: parent.width; height: 22; value: page.st.imgProgress }
        Item {
            width: parent.width; height: 22
            Txt {
                font.weight: Font.Bold
                text: qsTr("%1 % · %2 de %3").arg(Math.floor(page.st.imgProgress * 100))
                    .arg(backend.size(page.st.imgProgress * page.st.driveSize)).arg(backend.size(page.st.driveSize))
            }
            Txt {
                anchors.right: parent.right; color: Theme.soft; font.weight: Font.Bold
                text: page.st.imgRetrying ? qsTr("Reintentando las partes difíciles…")
                    : qsTr("%1/s · %2").arg(backend.size(page.st.imgSpeed)).arg(win.eta(page.st.imgEta))
            }
        }
        Rectangle {
            visible: page.st.imgBad > 0
            width: parent.width; height: 46; radius: 12; color: Theme.warnBg
            Txt {
                anchors.verticalCenter: parent.verticalCenter; x: 16; width: parent.width - 32
                color: Theme.warnInk; font.pixelSize: 15; font.weight: Font.Bold
                elide: Text.ElideRight; wrapMode: Text.NoWrap
                text: qsTr("Hay partes del pendrive que no se dejan leer (%1). Seguimos con todo lo demás.").arg(backend.size(page.st.imgBad))
            }
        }
        Card {
            width: parent.width; height: 52
            Txt {
                anchors.verticalCenter: parent.verticalCenter; x: 20; width: parent.width - 40
                font.pixelSize: 15; elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                text: qsTr("Se guarda en: %1").arg(page.st.imagePath)
            }
        }
    }

    Txt {
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.right: pause.left; anchors.margins: 32; anchors.leftMargin: 110
        color: Theme.soft; font.pixelSize: 15
        text: qsTr("No desconectes el pendrive todavía. Puedes pausar cuando quieras: la próxima vez sigue donde se quedó.")
    }
    Btn {
        id: pause
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 32; anchors.rightMargin: 110
        primary: false
        label: qsTr("Pausar")
        onClicked: backend.pauseImaging()
    }
}
