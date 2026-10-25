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
            text: qsTr("Copying your drive somewhere safe…"); font.pixelSize: 30; font.weight: Font.ExtraBold
        }
        Txt {
            width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.soft
            text: qsTr("First we make a full copy on your computer. That way, if the drive fails, nothing is lost. Then we look for your files in the copy.")
        }
        Bar { width: parent.width; height: 22; value: page.st.imgProgress }
        Item {
            width: parent.width; height: 22
            Txt {
                font.weight: Font.Bold
                text: qsTr("%1 % · %2 of %3").arg(Math.floor(page.st.imgProgress * 100))
                    .arg(backend.size(page.st.imgProgress * page.st.driveSize)).arg(backend.size(page.st.driveSize))
            }
            Txt {
                anchors.right: parent.right; color: Theme.soft; font.weight: Font.Bold
                text: page.st.imgRetrying ? qsTr("Retrying the hard parts…")
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
                text: qsTr("Some parts of the drive cannot be read (%1). We carry on with everything else.").arg(backend.size(page.st.imgBad))
            }
        }
        Card {
            width: parent.width; height: 52
            Txt {
                anchors.verticalCenter: parent.verticalCenter; x: 20; width: parent.width - 40
                font.pixelSize: 15; elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                text: qsTr("Saved in: %1").arg(page.st.imagePath)
            }
        }
    }

    Txt {
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.right: pause.left; anchors.margins: 32; anchors.leftMargin: 110
        color: Theme.soft; font.pixelSize: 15
        text: qsTr("Don't unplug the drive yet. You can pause at any time: next time it picks up where it left off.")
    }
    Btn {
        id: pause
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 32; anchors.rightMargin: 110
        primary: false
        label: qsTr("Pause")
        onClicked: backend.pauseImaging()
    }
}
