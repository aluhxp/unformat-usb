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
        anchors.margins: 32; anchors.leftMargin: 72; anchors.rightMargin: 72
        spacing: 20

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
        label: page.healthy ? qsTr("Buscar de todos modos") : qsTr("Empezar a buscar")
        onClicked: backend.scan()
    }
}
