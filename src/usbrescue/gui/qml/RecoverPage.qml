import QtQuick

Item {
    id: page
    readonly property var st: win.st

    Column {
        anchors.fill: parent
        anchors.margins: 40; anchors.leftMargin: 110; anchors.rightMargin: 110
        spacing: 22

        Mascot { width: 72; mood: "working"; anchors.horizontalCenter: parent.horizontalCenter }
        Txt {
            width: parent.width; horizontalAlignment: Text.AlignHCenter
            text: qsTr("Rescuing your files…"); font.pixelSize: 32; font.weight: Font.ExtraBold
        }
        Txt {
            width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.soft; font.pixelSize: 17
            text: (page.st.early ? qsTr("%1 of %2 so far. When this is done we keep searching for the rest.")
                                 : qsTr("%1 of %2 so far. You can keep using your computer."))
                .arg(win.num(page.st.recDone)).arg(win.num(page.st.recTotal))
        }
        Bar { width: parent.width; height: 22; value: page.st.recProgress }
        Item {
            width: parent.width; height: 22
            Txt { text: qsTr("%1 %").arg(Math.floor(page.st.recProgress * 100)); font.weight: Font.Bold }
            Txt {
                anchors.right: parent.right; color: Theme.soft; font.weight: Font.Bold
                text: qsTr("%1/s · %2").arg(backend.size(page.st.recSpeed)).arg(win.eta(page.st.recEta))
            }
        }
        Card {
            width: parent.width; height: 92
            Column {
                anchors.fill: parent; anchors.margins: 16; anchors.leftMargin: 20; anchors.rightMargin: 20
                spacing: 10
                Txt { width: parent.width; font.pixelSize: 15; elide: Text.ElideMiddle; wrapMode: Text.NoWrap; text: qsTr("Now: %1").arg(page.st.recCurrent) }
                Txt { width: parent.width; font.pixelSize: 15; elide: Text.ElideMiddle; wrapMode: Text.NoWrap; text: qsTr("Saved in: %1").arg(page.st.destPath) }
            }
        }
        Rectangle {
            width: parent.width; height: 46; radius: 12; color: Theme.warnBg
            Txt {
                anchors.verticalCenter: parent.verticalCenter; x: 16
                color: Theme.warnInk; font.pixelSize: 15; font.weight: Font.Bold
                text: qsTr("Don't unplug the drive until we are done.")
            }
        }
    }
}
