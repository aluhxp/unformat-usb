import QtQuick

// The little pen drive. mood: "calm" | "happy" | "working" | "sorry"
Item {
    id: root
    property string mood: "calm"
    property real unit: width / 30
    width: 60
    height: width * 1.2
    Accessible.ignored: true

    Rectangle { x: 9 * unit; y: 1 * unit; width: 12 * unit; height: 10 * unit; radius: 2 * unit; color: "#B9C9C2" }
    Rectangle { x: 2 * unit; y: 9 * unit; width: 26 * unit; height: 26 * unit; radius: 8 * unit; color: Theme.sun }
    Repeater {
        model: [9.5, 17.5]
        Rectangle {
            required property real modelData
            x: modelData * root.unit
            y: (root.mood === "happy" ? 20.5 : 19.5) * root.unit
            width: 3.2 * root.unit
            height: (root.mood === "happy" ? 1.6 : 3.2) * root.unit
            radius: width / 2
            color: Theme.sunInk
        }
    }
    Rectangle {
        // mouth: a smile is a rounded bar; "sorry" and "working" flatten it
        x: (root.mood === "happy" ? 10 : 12) * unit
        y: 25.5 * unit
        width: (root.mood === "happy" ? 10 : 6) * unit
        height: (root.mood === "happy" ? 4.5 : 1.8) * unit
        radius: height / 2
        bottomLeftRadius: root.mood === "happy" ? 5 * unit : height / 2
        bottomRightRadius: root.mood === "happy" ? 5 * unit : height / 2
        topLeftRadius: root.mood === "happy" ? unit : height / 2
        topRightRadius: root.mood === "happy" ? unit : height / 2
        color: Theme.sunInk
    }
}
