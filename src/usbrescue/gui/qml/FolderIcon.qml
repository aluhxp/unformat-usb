import QtQuick

Item {
    property bool faded: false
    width: 24; height: 20
    Accessible.ignored: true
    Rectangle { x: 0; y: 0; width: 11; height: 7; radius: 2; color: parent.faded ? Theme.line : Theme.sun }
    Rectangle { x: 0; y: 4; width: 24; height: 16; radius: 3; color: parent.faded ? Theme.line : Theme.sun }
}
