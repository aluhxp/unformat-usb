import QtQuick

Item {
    id: page
    readonly property var st: win.st
    readonly property bool busy: st.phase === "diagnosing"
    readonly property bool good: st.verdict === "names_and_structure" || st.verdict === "structure"
    readonly property bool healthy: st.verdict === "in_use"

    readonly property var headline: ({
        in_use: qsTr("Este pendrive parece estar bien."),
        names_and_structure: qsTr("Muy buenas noticias: tus carpetas siguen ahí, con sus nombres."),
        structure: qsTr("Buenas noticias: tus carpetas siguen ahí."),
        scan_needed: qsTr("Vamos a buscar a fondo."),
        looks_empty: qsTr("Este pendrive parece vacío.")
    })
    readonly property var detail: ({
        in_use: qsTr("Sus archivos están a la vista y no vemos señales de un formateo reciente: puedes abrirlos con normalidad, no hace falta rescatarlos."),
        names_and_structure: qsTr("Revisamos el pendrive en un momento. Esto es lo que dejó el formateo:"),
        structure: qsTr("Revisamos el pendrive en un momento. Esto es lo que dejó el formateo:"),
        scan_needed: qsTr("El formateo borró el índice, pero los archivos pueden seguir ahí. Solo la búsqueda completa lo dirá."),
        looks_empty: qsTr("Todo lo que miramos está en blanco: o no tenía datos, o se borraron al formatear. La búsqueda completa lo confirma.")
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
                    text: page.busy ? qsTr("Revisando %1…").arg(page.st.sourceName) : (page.headline[page.st.verdict] || "")
                    font.pixelSize: 30; font.weight: Font.ExtraBold
                }
                Txt {
                    width: parent.width; color: Theme.soft
                    text: !page.busy ? (page.detail[page.st.verdict] || "")
                        : page.st.needsPermission
                        ? qsTr("El sistema te pedirá la contraseña para poder leer el pendrive. Solo lo leemos: no se escribe nada en él.")
                        : qsTr("Son solo unos segundos.")
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
                    text: qsTr("Lo que tiene ahora: %1 carpetas y %2 archivos sueltos").arg(win.num(page.st.currentFolderCount)).arg(win.num(page.st.currentFiles))
                }
                Txt {
                    visible: page.st.currentFolders.length > 0
                    width: parent.width; color: Theme.soft; font.pixelSize: 15
                    elide: Text.ElideRight; wrapMode: Text.NoWrap
                    text: page.st.currentFolders.join(" · ") + (page.st.currentFolderCount > page.st.currentFolders.length ? " …" : "")
                }
                Txt {
                    width: parent.width; color: Theme.soft; font.pixelSize: 15
                    text: qsTr("¿Buscas algo que borraste, o lo que había antes de un formateo? Entonces sí podemos buscar: lo que ya no está a la vista a veces sigue en el pendrive.")
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
                        { what: qsTr("Las carpetas y lo que tenían dentro"),
                          ok: page.good, text: page.good ? qsTr("Se pueden reconstruir") : qsTr("Lo sabremos al buscar") },
                        { what: qsTr("Los archivos grandes guardados en trozos"),
                          ok: page.st.diagFat, text: page.st.diagFat ? qsTr("Se pueden rearmar") : qsTr("Algunos podrían salir dañados") },
                        { what: qsTr("Los nombres de las carpetas principales"),
                          ok: page.st.diagRoot, text: page.st.diagRoot ? qsTr("Se conservan") : qsTr("Probablemente se perdieron") }
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
        Txt { text: qsTr("¿Cómo quieres hacerlo?"); font.weight: Font.ExtraBold }
        Row {
            width: parent.width; spacing: 14
            Repeater {
                model: [
                    { mode: "safe", title: qsTr("Modo seguro"),
                      text: !page.st.safeFits
                        ? qsTr("No hay espacio: la copia necesita %1 y tienes %2 libres.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace))
                        : page.st.safeRoomy
                        ? qsTr("Primero copiamos el pendrive entero a tu computadora y trabajamos sobre la copia. Necesita %1; tienes %2 libres.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace))
                        : qsTr("La copia cabe (%1 de %2 libres), pero puede que después no quede sitio para todo lo rescatado.").arg(backend.size(page.st.driveSize)).arg(backend.size(page.st.freeSpace)) },
                    { mode: "direct", title: qsTr("Modo directo"),
                      text: qsTr("Leemos directamente del pendrive. Empieza antes, pero si el pendrive está fallando es más arriesgado.") }
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
                        Txt { id: rec; anchors.centerIn: parent; text: qsTr("Recomendado"); color: Theme.sunInk; font.pixelSize: 12; font.weight: Font.ExtraBold }
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
        Btn { label: qsTr("Elegir otro"); primary: false; onClicked: backend.back() }
    }
    Btn {
        visible: !page.busy
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 32; anchors.rightMargin: 72
        primary: !page.healthy
        label: page.healthy ? qsTr("Buscar de todos modos")
            : page.st.mode === "safe" ? qsTr("Hacer la copia y buscar") : qsTr("Empezar a buscar")
        onClicked: backend.start()
    }
}
