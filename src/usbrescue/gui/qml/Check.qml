import QtQuick

Rectangle {
    id: root
    property bool checked: false
    property string name
    signal toggled(bool value)

    width: 22; height: 22; radius: 6
    color: checked ? Theme.accent : "transparent"
    border.color: checked ? Theme.accent : Theme.soft
    border.width: 2
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: name
    Accessible.checked: checked
    Keys.onSpacePressed: root.toggled(!checked)

    // the tick
    Rectangle { visible: root.checked; x: 5; y: 10; width: 6; height: 2.6; radius: 1; rotation: 45; color: Theme.accentText }
    Rectangle { visible: root.checked; x: 8; y: 9; width: 11; height: 2.6; radius: 1; rotation: -50; color: Theme.accentText }
    Rectangle {
        anchors.fill: parent; anchors.margins: -4; radius: 9; color: "transparent"
        border.color: Theme.ink; border.width: 2; visible: root.activeFocus
    }
    MouseArea {
        anchors.fill: parent; anchors.margins: -11
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
