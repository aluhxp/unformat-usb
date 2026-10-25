import QtQuick
import QtQuick.Controls.Basic

Item {
    id: page
    readonly property var st: win.st

    Column {
        anchors.fill: parent
        anchors.margins: 26; anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 16

        Row {
            spacing: 22; width: parent.width
            Mascot { width: 84; mood: "happy" }
            Column {
                width: parent.width - 106; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Txt {
                    width: parent.width; font.pixelSize: 32; font.weight: Font.ExtraBold
                    text: qsTr("Done! We rescued %1 files.").arg(win.num(page.st.sumOk + page.st.sumWarned + page.st.sumOrphans))
                }
                Txt { width: parent.width; color: Theme.soft; elide: Text.ElideMiddle; wrapMode: Text.NoWrap; text: qsTr("They are in %1").arg(page.st.destPath) }
                Txt { width: parent.width; color: Theme.soft; font.pixelSize: 14; text: qsTr("Before using the drive again, open a few important files to check they are fine.") }
            }
        }

        Row {
            width: parent.width; spacing: 14
            Repeater {
                model: [
                    { n: page.st.sumOk, label: qsTr("came out fine"), tone: Theme.accent },
                    { n: page.st.sumWarned, label: qsTr("worth checking"), tone: page.st.sumWarned ? Theme.warn : Theme.ink },
                    { n: page.st.sumOrphans, label: qsTr("loose, without a folder"), tone: Theme.ink },
                    { n: page.st.sumUnnamed, label: qsTr("unnamed folders"), tone: page.st.sumUnnamed ? Theme.warn : Theme.ink }
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
            Btn { label: qsTr("Open the folder"); onClicked: backend.openDestination() }
            Btn { label: qsTr("See the report"); primary: false; onClicked: backend.openReport() }
            Btn { label: qsTr("Rescue another drive"); primary: false; onClicked: backend.back() }
        }

        Row {
            visible: page.st.sumUnnamed > 0 || page.st.renamed > 0
            spacing: 14
            Txt {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, page.width - 144 - nameBtn.width - 14)
                font.pixelSize: 15
                text: page.st.renamed > 0
                    ? qsTr("We named %1 folders.").arg(win.num(page.st.renamed))
                    : qsTr("%1 folders lost their name. We can suggest one for each.").arg(win.num(page.st.sumUnnamed))
            }
            Btn {
                id: nameBtn
                label: page.st.renamed > 0 ? qsTr("Undo") : qsTr("Name them")
                primary: false; implicitHeight: 40
                onClicked: page.st.renamed > 0 ? backend.undoNames() : backend.suggestNames()
            }
        }

        Row {
            visible: page.st.imageMade
            spacing: 14
            Txt {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, page.width - 144 - drop.width - 14)
                font.pixelSize: 15
                text: qsTr("The safety copy takes %1. Once you have checked your files, you can delete it.").arg(backend.size(page.st.driveSize))
            }
            Btn { id: drop; label: qsTr("Delete the copy"); primary: false; implicitHeight: 40; onClicked: backend.deleteCopy() }
        }

    }

    // A voluntary thank-you, only after a rescue that worked. It never blocks anything.
    Rectangle {
        id: donation
        visible: backend.canDonate && page.st.sumOk + page.st.sumWarned + page.st.sumOrphans > 0
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 22; anchors.leftMargin: 72; anchors.rightMargin: 72
        height: 84; radius: 18
        color: Theme.warnBg; border.color: Theme.sun; border.width: 1

        Column {
            anchors.left: parent.left; anchors.leftMargin: 22
            anchors.right: amounts.left; anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Txt { width: parent.width; font.pixelSize: 17; font.weight: Font.ExtraBold; text: qsTr("Did it help? Buy us a coffee.") }
            Txt { width: parent.width; font.pixelSize: 13; color: Theme.warnInk; text: qsTr("It's optional. %1 is free, with no limits, and it will stay that way.").arg(appName) }
        }
        Row {
            id: amounts
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Repeater {
                model: backend.donationAmounts
                Btn {
                    required property var modelData
                    required property int index
                    label: modelData + " " + backend.donationCurrency
                    primary: index === 1
                    implicitHeight: 42; implicitWidth: 84
                    onClicked: backend.donate(String(modelData))
                }
            }
            TextField {
                id: other
                width: 136; height: 42
                placeholderText: qsTr("Other amount")
                placeholderTextColor: Theme.soft
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                font.family: Theme.family; font.pixelSize: 15; font.weight: Font.Bold
                color: Theme.ink
                Accessible.name: qsTr("Other amount, in %1").arg(backend.donationCurrency)
                background: Rectangle {
                    radius: 21; color: Theme.card
                    border.color: other.activeFocus ? Theme.accent : Theme.line
                    border.width: other.activeFocus ? 2 : 1
                }
                leftPadding: 16
                onAccepted: if (backend.donationAmountOk(text)) backend.donate(text)
            }
            Btn {
                label: qsTr("Donate")
                implicitHeight: 42
                visible: other.text.length > 0
                enabledLook: backend.donationAmountOk(other.text)
                onClicked: backend.donate(other.text)
            }
        }
    }
}
