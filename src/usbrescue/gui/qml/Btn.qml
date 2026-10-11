import QtQuick

Rectangle {
    id: root
    property string label
    property bool primary: true
    property bool enabledLook: true
    signal clicked()

    implicitHeight: 52
    implicitWidth: text.implicitWidth + 56
    radius: height / 2
    color: primary ? Theme.accent : "transparent"
    border.color: Theme.accent
    border.width: primary ? 0 : 2
    opacity: enabledLook ? (area.pressed ? 0.85 : 1) : 0.45
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label
    Keys.onReturnPressed: if (enabledLook) root.clicked()
    Keys.onSpacePressed: if (enabledLook) root.clicked()

    Txt {
        id: text
        anchors.centerIn: parent
        text: root.label
        color: root.primary ? Theme.accentText : Theme.accent
        font.pixelSize: 17
        font.weight: Font.ExtraBold
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -4
        radius: height / 2
        color: "transparent"
        border.color: Theme.ink
        border.width: 2
        visible: root.activeFocus
    }
    MouseArea {
        id: area
        anchors.fill: parent
        enabled: root.enabledLook
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
