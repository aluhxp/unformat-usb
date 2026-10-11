import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Item {
    id: page
    readonly property var st: win.st
    readonly property bool scanning: st.phase === "scanning"
    property string destination: backend.defaultDestination

    Column {
        id: top
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 20; anchors.leftMargin: 32; anchors.rightMargin: 32
        spacing: 10
        Item {
            width: parent.width; height: title.implicitHeight
            Txt {
                id: title
                width: parent.width - 290
                font.pixelSize: 23; font.weight: Font.ExtraBold
                text: page.st.foundFolders === 0
                    ? qsTr("Buscando tus carpetas…")
                    : (page.scanning ? qsTr("Ya encontramos %1 archivos en %2 carpetas") : qsTr("Encontramos %1 archivos en %2 carpetas"))
                        .arg(win.num(page.st.foundFiles)).arg(win.num(page.st.foundFolders))
            }
            Txt {
                anchors.right: parent.right; anchors.baseline: title.baseline
                color: Theme.soft; font.pixelSize: 15
                text: page.scanning && page.st.scanProgress >= 1
                    ? qsTr("Ordenando lo encontrado…")
                    : page.scanning
                    ? qsTr("Buscando: %1 % · %2").arg(Math.floor(page.st.scanProgress * 100)).arg(win.eta(page.st.scanEta))
                    : qsTr("Búsqueda terminada · %1").arg(backend.size(page.st.foundBytes))
            }
        }
        Bar { width: parent.width; value: page.st.scanProgress }
    }

    Card {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: top.bottom; anchors.bottom: bottom.top
        anchors.margins: 16; anchors.leftMargin: 32; anchors.rightMargin: 32

        Txt {
            visible: list.count === 0
            anchors.centerIn: parent
            color: Theme.soft
            text: qsTr("Las carpetas irán apareciendo aquí.")
        }

        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 8
            clip: true
            model: backend.tree
            ScrollBar.vertical: ScrollBar {}
            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 } }
            delegate: Rectangle {
                id: row
                required property int index
                required property string name
                required property int depth
                required property int totalFiles
                required property double totalSize
                required property bool checked
                required property bool expanded
                required property bool hasChildren
                required property bool lostName
                required property bool isPending
                required property bool isGroup
                width: list.width - 12
                height: 44
                radius: 10
                color: hover.hovered && !isGroup ? Theme.rowHover : "transparent"
                HoverHandler { id: hover }

                Txt {
                    visible: row.isGroup
                    anchors.verticalCenter: parent.verticalCenter; x: 8
                    color: Theme.soft; font.pixelSize: 14; font.weight: Font.ExtraBold
                    text: qsTr("Ubicando: carpetas que todavía no sabemos dónde van")
                }
                Row {
                    visible: !row.isGroup
                    anchors.verticalCenter: parent.verticalCenter
                    x: 8 + Math.max(0, row.depth) * 26
                    spacing: 10
                    Item {
                        width: 20; height: 22
                        anchors.verticalCenter: parent.verticalCenter
                        Txt {
                            visible: row.hasChildren
                            anchors.centerIn: parent
                            text: "›"; font.pixelSize: 22; font.weight: Font.Bold; color: Theme.soft
                            rotation: row.expanded ? 90 : 0
                        }
                        TapHandler { enabled: row.hasChildren; onTapped: backend.toggleExpanded(row.index) }
                    }
                    Check {
                        anchors.verticalCenter: parent.verticalCenter
                        checked: row.checked; name: row.name
                        onToggled: (value) => backend.setChecked(row.index, value)
                    }
                    FolderIcon { anchors.verticalCenter: parent.verticalCenter; faded: row.isPending || row.lostName }
                    Txt { anchors.verticalCenter: parent.verticalCenter; text: row.name; font.weight: Font.Bold; wrapMode: Text.NoWrap }
                    Rectangle {
                        visible: row.lostName
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.warnBg; radius: 11; height: 22; width: lost.implicitWidth + 16
                        Txt { id: lost; anchors.centerIn: parent; text: qsTr("Nombre perdido"); color: Theme.warnInk; font.pixelSize: 13; font.weight: Font.ExtraBold }
                    }
                }
                Txt {
                    visible: !row.isGroup
                    anchors.right: parent.right; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.soft; font.pixelSize: 14
                    text: qsTr("%1 archivos · %2").arg(win.num(row.totalFiles)).arg(backend.size(row.totalSize))
                }
            }
        }
    }

    Item {
        id: bottom
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 20; anchors.leftMargin: 32; anchors.rightMargin: 32
        height: 84

        Column {
            anchors.left: parent.left; anchors.right: go.left; anchors.rightMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Row {
                visible: !page.scanning && page.st.orphanCount > 0
                spacing: 10
                Check {
                    checked: page.st.withOrphans
                    name: qsTr("Incluir archivos sin carpeta")
                    onToggled: (value) => backend.setWithOrphans(value)
                }
                Txt {
                    font.pixelSize: 15
                    text: qsTr("Incluir %1 archivos sin carpeta (los que estaban sueltos, fuera de las carpetas)").arg(win.num(page.st.orphanCount))
                }
            }
            Row {
                spacing: 10
                Txt {
                    color: Theme.soft; font.pixelSize: 15
                    width: Math.min(implicitWidth, bottom.width - go.width - 150)
                    elide: Text.ElideMiddle; wrapMode: Text.NoWrap
                    text: page.scanning ? qsTr("Podrás rescatar en cuanto termine la búsqueda.") : qsTr("Se guardará en: %1").arg(page.destination)
                }
                Txt {
                    visible: !page.scanning
                    text: qsTr("Cambiar…"); color: Theme.accent; font.pixelSize: 15; font.weight: Font.Bold
                    TapHandler { onTapped: folderDialog.open() }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
            }
        }
        Btn {
            id: go
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            enabledLook: !page.scanning && page.st.selectedFiles + (page.st.withOrphans ? page.st.orphanCount : 0) > 0
            label: qsTr("Rescatar lo marcado (%1)").arg(backend.size(page.st.selectedBytes))
            onClicked: backend.recover(page.destination)
        }
    }

    FolderDialog {
        id: folderDialog
        title: qsTr("¿Dónde guardamos lo rescatado?")
        onAccepted: page.destination = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }
}
