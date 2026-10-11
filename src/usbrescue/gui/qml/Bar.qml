import QtQuick

Rectangle {
    property real value: 0
    height: 14
    radius: height / 2
    color: Theme.line
    Accessible.role: Accessible.ProgressBar

    Rectangle {
        height: parent.height
        radius: parent.radius
        width: Math.max(parent.height, parent.width * Math.min(1, Math.max(0, parent.value)))
        color: Theme.accent
        Behavior on width { NumberAnimation { duration: 200 } }
    }
}
