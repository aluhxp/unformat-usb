import QtQuick

Item {
    id: page
    readonly property var st: win.st
    readonly property bool busy: st.phase === "diagnosing"
    readonly property bool good: st.verdict === "names_and_structure" || st.verdict === "structure"
    readonly property bool healthy: st.verdict === "in_use"

    readonly property var headline: ({
        in_use: qsTr("This drive looks fine."),
        names_and_structure: qsTr("Great news: your folders are still there, with their names."),
        structure: qsTr("Good news: your folders are still there."),
        scan_needed: qsTr("Let's search it thoroughly."),
        looks_empty: qsTr("This drive looks empty.")
    })
    readonly property var detail: ({
        in_use: qsTr("Its files are in plain sight and we see no sign of a recent format: you can open them as usual, there is nothing to rescue."),
        names_and_structure: qsTr("We took a quick look at the drive. This is what the format left behind:"),
        structure: qsTr("We took a quick look at the drive. This is what the format left behind:"),
        scan_needed: qsTr("The format erased the index, but the files may still be there. Only a full search will tell."),
        looks_empty: qsTr("Everything we looked at is blank: either it held no data, or the format erased it. A full search will confirm it.")
    })

    Column {
        anchors.fill: parent
        anchors.margins: 24; anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 14

        Row {
            spacing: 22
            width: parent.width
            Mascot { width: 84; mood: page.busy ? "working" : page.good || page.healthy ? "happy" : "calm" }
            Column {
                width: parent.width - 106
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                Txt {
                    width: parent.width
                    text: page.busy ? qsTr("Checking %1…").arg(page.st.sourceName) : (page.headline[page.st.verdict] || "")
                    font.pixelSize: 30; font.weight: Font.ExtraBold
                }
                Txt {
                    width: parent.width; color: Theme.soft
                    text: !page.busy ? (page.detail[page.st.verdict] || "")
                        : page.st.needsPermission
                        ? qsTr("Your system will ask for your password so the drive can be read. We only read it: nothing is written to it.")
                        : qsTr("It only takes a few seconds.")
                }
            }
        }

        Card {
            visible: page.healthy && !page.busy
            width: parent.width
            height: seen.implicitHeight + 36
            Column {
                id: seen
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 18; anchors.leftMargin: 20; anchors.rightMargin: 20
                spacing: 8
                Txt {
                    width: parent.width; font.weight: Font.Bold
                    text: qsTr("What it holds now: %1 folders and %2 loose files").arg(win.num(page.st.currentFolderCount)).arg(win.num(page.st.currentFiles))
                }
                Txt {
                    visible: page.st.currentFolders.length > 0
                    width: parent.width; color: Theme.soft; font.pixelSize: 15
                    elide: Text.ElideRight; wrapMode: Text.NoWrap
                    text: page.st.currentFolders.join(" · ") + (page.st.currentFolderCount > page.st.currentFolders.length ? " …" : "")
                }
                Txt {
                    width: parent.width; color: Theme.soft; font.pixelSize: 15
                    text: qsTr("Looking for something you deleted, or for what was there before a format? Then a search is worth it: what is no longer in sight is sometimes still on the drive.")
                }
            }
        }

        Card {
            visible: !page.busy && !page.healthy
            width: parent.width
            height: rows.implicitHeight + 12
            Column {
                id: rows
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 6; anchors.leftMargin: 20; anchors.rightMargin: 20
                Repeater {
                    model: [
                        { what: qsTr("The folders and what was inside them"),
                          ok: page.good, text: page.good ? qsTr("Can be rebuilt") : qsTr("We'll know after searching") },
                        { what: qsTr("Large files stored in pieces"),
                          ok: page.st.diagFat, text: page.st.diagFat ? qsTr("Can be put back together") : qsTr("Some may come out damaged") },
                        { what: qsTr("The names of the main folders"),
                          ok: page.st.diagRoot, text: page.st.diagRoot ? qsTr("Kept") : qsTr("Probably lost") }
                    ]
                    Item {
                        required property var modelData
                        required property int index
                        width: rows.width; height: 50
                        Rectangle { visible: parent.index > 0; width: parent.width; height: 1; color: Theme.line }
                        Rectangle {
                            id: dot
                            anchors.verticalCenter: parent.verticalCenter
                            width: 14; height: 14; radius: parent.modelData.ok ? 7 : 3
                            color: parent.modelData.ok ? Theme.accent : Theme.warn
                        }
                        Txt { anchors.left: dot.right; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData.what; font.weight: Font.Bold }
                        Txt {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            text: parent.modelData.text; font.pixelSize: 15; font.weight: Font.Bold
                            color: parent.modelData.ok ? Theme.accent : Theme.warn
                        }
                    }
                }
            }
        }
    }

    // how to go about it: only a real drive can fail while being read
    Column {
        visible: !page.busy && page.st.isDevice
        anchors.left: parent.left; anchors.right: parent.right
        anchors.bottom: parent.bottom; anchors.bottomMargin: 106
        anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 8
        Txt { text: qsTr("How would you like to do it?"); font.weight: Font.ExtraBold }
        Row {
            width: parent.width; spacing: 14
            Repeater {
                model: [
                    { mode: "safe", title: qsTr("Safe mode"),
                      text: !page.st.safeFits
                        ? qsTr("Not enough space: the copy needs %1 and you have %2 free.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace))
                        : page.st.safeRoomy
                        ? qsTr("First we copy the whole drive to your computer and work on the copy. Needs %1; %2 free.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace))
                        : qsTr("The copy fits (%1 of %2 free), but there may be no room left afterwards for everything rescued.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace)) },
                    { mode: "direct", title: qsTr("Direct mode"),
                      text: qsTr("We read straight from the drive. It starts sooner, but it is riskier if the drive is failing.") }
                ]
                Card {
                    id: option
                    required property var modelData
                    readonly property bool chosen: page.st.mode === modelData.mode
                    readonly property bool usable: modelData.mode === "direct" || page.st.safeFits
                    width: (parent.width - 14) / 2
                    height: 104
                    border.width: 2
                    border.color: chosen ? Theme.accent : Theme.line
                    opacity: usable ? 1 : 0.6
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.title
                    Accessible.checked: chosen
                    Keys.onSpacePressed: backend.setMode(modelData.mode)
                    TapHandler { enabled: option.usable; onTapped: backend.setMode(option.modelData.mode) }
                    HoverHandler { cursorShape: option.usable ? Qt.PointingHandCursor : Qt.ArrowCursor }
                    Rectangle {
                        id: radio
                        x: 16; y: 16; width: 20; height: 20; radius: 10
                        color: "transparent"; border.width: 2
                        border.color: option.chosen ? Theme.accent : Theme.soft
                        Rectangle { visible: option.chosen; anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: Theme.accent }
                    }
                    Txt {
                        id: optionTitle
                        anchors.left: radio.right; anchors.leftMargin: 12; y: 13
                        text: option.modelData.title; font.pixelSize: 17; font.weight: Font.ExtraBold
                    }
                    Rectangle {
                        visible: option.modelData.mode === "safe" && page.st.safeRoomy
                        anchors.left: optionTitle.right; anchors.leftMargin: 10
                        anchors.verticalCenter: optionTitle.verticalCenter
                        color: Theme.sun; radius: 10; height: 20; width: rec.implicitWidth + 16
                        Txt { id: rec; anchors.centerIn: parent; text: qsTr("Recommended"); color: Theme.sunInk; font.pixelSize: 12; font.weight: Font.ExtraBold }
                    }
                    Txt {
                        anchors.left: radio.right; anchors.leftMargin: 12
                        anchors.right: parent.right; anchors.rightMargin: 14
                        y: 40
                        color: Theme.soft; font.pixelSize: 14
                        maximumLineCount: 3; elide: Text.ElideRight
                        text: option.modelData.text
                    }
                }
            }
        }
    }

    Row {
        visible: !page.busy
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.margins: 32; anchors.leftMargin: 72
        Btn { label: qsTr("Choose another"); primary: false; onClicked: backend.back() }
    }
    Btn {
        visible: !page.busy
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 32; anchors.rightMargin: 72
        primary: !page.healthy
        label: page.healthy ? qsTr("Search anyway")
            : page.st.mode === "safe" ? qsTr("Make the copy and search") : qsTr("Start searching")
        onClicked: backend.start()
    }
}
