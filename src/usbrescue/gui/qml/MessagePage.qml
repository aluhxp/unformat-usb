import QtQuick

Item {
    id: page
    readonly property var st: win.st
    readonly property string code: st.phase === "nothing" ? "nothing" : (st.error.startsWith("io:") ? "io" : st.error)

    readonly property var headline: ({
        nothing: qsTr("We found no folders on this drive."),
        no_permission: qsTr("We are not allowed to read this drive."),
        same_device: qsTr("Choose another place to save to."),
        io: qsTr("We could not read the drive.")
    })
    readonly property var detail: ({
        nothing: qsTr("It may have had a full format, which erases everything, or used another file system. It's not your fault, and we're sorry."),
        no_permission: backend.canRestartAsAdmin
            ? qsTr("Windows only lets an administrator read a whole drive. Open %1 as administrator: Windows will ask you to confirm.").arg(appName)
            : qsTr("Your system only lets a whole drive be read with the administrator password. If you closed the password window, choose the drive again and retry."),
        same_device: qsTr("The chosen folder is on the very drive you want to rescue. Saving there would cover up the files we are looking for."),
        io: qsTr("Check that it is still plugged in and try again. Details: %1").arg(st.error.slice(3))
    })

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 144, 620)
        spacing: 18
        Mascot { width: 84; mood: "sorry"; anchors.horizontalCenter: parent.horizontalCenter }
        Txt { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 28; font.weight: Font.ExtraBold; text: page.headline[page.code] || "" }
        Txt { width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.soft; text: page.detail[page.code] || "" }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 14
            Btn {
                visible: page.code === "no_permission" && backend.canRestartAsAdmin
                label: qsTr("Open as administrator")
                onClicked: backend.restartAsAdmin()
            }
            Btn {
                label: qsTr("Back to the start")
                primary: !(page.code === "no_permission" && backend.canRestartAsAdmin)
                onClicked: backend.back()
            }
        }
    }
}
