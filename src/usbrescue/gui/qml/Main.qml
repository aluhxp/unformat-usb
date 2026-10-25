import QtQuick
import QtQuick.Controls.Basic

ApplicationWindow {
    id: win
    width: 960
    height: 640
    minimumWidth: 820
    minimumHeight: 560
    visible: true
    title: appName
    color: Theme.bg

    // lets a test or a screenshot tool pick the theme
    property bool forceDark: Theme.dark
    onForceDarkChanged: Theme.dark = forceDark

    readonly property var st: backend.state
    readonly property int step: ["pick", "error"].indexOf(st.phase) >= 0 ? 1
        : ["recovering", "done", "naming"].indexOf(st.phase) >= 0 ? 3 : 2

    function num(n) { return Number(n).toLocaleString(Qt.locale(backend.locale), "f", 0) }
    function eta(seconds) {
        if (seconds < 0) return qsTr("working out the time…")
        if (seconds < 60) return qsTr("less than a minute left")
        return qsTr("about %1 min left").arg(Math.round(seconds / 60))
    }

    header: Item {
        height: 64
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }
        Row {
            anchors.left: parent.left; anchors.leftMargin: 32
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Mascot { width: 30; anchors.verticalCenter: parent.verticalCenter }
            Txt { text: appName; font.pixelSize: 20; font.weight: Font.ExtraBold; anchors.verticalCenter: parent.verticalCenter }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 32
            anchors.verticalCenter: parent.verticalCenter
            spacing: 18
            Repeater {
                model: [qsTr("1 Choose"), qsTr("2 Review"), qsTr("3 Recover")]
                Txt {
                    required property string modelData
                    required property int index
                    text: modelData
                    font.pixelSize: 14; font.weight: Font.Bold
                    color: win.step === index + 1 ? Theme.accent : Theme.soft
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Btn {
                id: langBtn
                objectName: "languageButton"
                label: backend.languageName + "  ▾"
                primary: false
                implicitHeight: 34
                anchors.verticalCenter: parent.verticalCenter
                Accessible.name: "Language · Idioma"
                onClicked: langMenu.open()

                Popup {
                    id: langMenu
                    y: langBtn.height + 6
                    x: langBtn.width - width
                    padding: 6
                    background: Rectangle {
                        color: Theme.card; radius: 14
                        border.color: Theme.line; border.width: 1
                    }
                    contentItem: Column {
                        Repeater {
                            model: backend.languages
                            Rectangle {
                                required property var modelData
                                width: 168; height: 38; radius: 10
                                color: pick.containsMouse ? Theme.rowHover : "transparent"
                                Accessible.role: Accessible.MenuItem
                                Accessible.name: modelData.name
                                Txt {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: 14
                                    text: modelData.name
                                    font.pixelSize: 15
                                    font.weight: modelData.code === backend.language ? Font.ExtraBold : Font.Normal
                                    color: modelData.code === backend.language ? Theme.accent : Theme.ink
                                }
                                MouseArea {
                                    id: pick
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: { langMenu.close(); backend.setLanguage(parent.modelData.code) }
                                }
                            }
                        }
                    }
                }
            }
            Btn {
                label: Theme.dark ? qsTr("Light") : qsTr("Dark")
                primary: false
                implicitHeight: 34
                anchors.verticalCenter: parent.verticalCenter
                onClicked: Theme.dark = !Theme.dark
            }
        }
    }

    Loader {
        objectName: "pages"
        anchors.fill: parent
        source: ({
            pick: "PickPage.qml", diagnosing: "DiagnosisPage.qml", diagnosed: "DiagnosisPage.qml",
            imaging: "ImagingPage.qml",
            scanning: "TreePage.qml", scanned: "TreePage.qml", recovering: "RecoverPage.qml",
            done: "DonePage.qml", naming: "NamesPage.qml", nothing: "MessagePage.qml", error: "MessagePage.qml"
        })[win.st.phase]
    }
}
