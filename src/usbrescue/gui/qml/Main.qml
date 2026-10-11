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
        : ["recovering", "done"].indexOf(st.phase) >= 0 ? 3 : 2

    function num(n) { return Number(n).toLocaleString(Qt.locale("es_ES"), "f", 0) }
    function eta(seconds) {
        if (seconds < 0) return qsTr("calculando el tiempo…")
        if (seconds < 60) return qsTr("falta menos de un minuto")
        return qsTr("faltan unos %1 min").arg(Math.round(seconds / 60))
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
                model: [qsTr("1 Elegir"), qsTr("2 Revisar"), qsTr("3 Recuperar")]
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
                label: Theme.dark ? qsTr("Claro") : qsTr("Oscuro")
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
            done: "DonePage.qml", nothing: "MessagePage.qml", error: "MessagePage.qml"
        })[win.st.phase]
    }
}
