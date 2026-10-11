pragma Singleton
import QtQuick

// Every colour and the typeface live here. Screens never hard-code them, so
// the dark variant and any restyling happen in this one file.
QtObject {
    property bool dark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark

    readonly property color bg: dark ? "#10201C" : "#F3F7F4"
    readonly property color card: dark ? "#19302A" : "#FFFFFF"
    readonly property color line: dark ? "#2B4A41" : "#DCE7E1"
    readonly property color rowHover: dark ? "#213D35" : "#EAF4EF"
    readonly property color ink: dark ? "#EAF4EF" : "#17302B"
    readonly property color soft: dark ? "#A9C2B8" : "#3F564F"
    readonly property color accent: dark ? "#3FC79E" : "#147A5E"
    // (a name starting with "on" would be read as a signal handler)
    readonly property color accentText: dark ? "#0B1F19" : "#FFFFFF"
    readonly property color warn: dark ? "#F1C56B" : "#8A5200"
    readonly property color warnBg: dark ? "#3A2F12" : "#FFE9B8"
    readonly property color warnInk: dark ? "#F6DFA6" : "#6B4000"
    readonly property color sun: "#FFC857"
    readonly property color sunInk: "#17302B"
    readonly property string family: "Nunito"
}
