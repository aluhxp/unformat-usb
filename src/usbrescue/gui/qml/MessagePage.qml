import QtQuick

Item {
    id: page
    readonly property var st: win.st
    readonly property string code: st.phase === "nothing" ? "nothing" : (st.error.startsWith("io:") ? "io" : st.error)

    readonly property var headline: ({
        nothing: qsTr("No encontramos carpetas en este pendrive."),
        no_permission: qsTr("Hace falta permiso para leer este pendrive."),
        same_device: qsTr("Elige otro lugar para guardar."),
        io: qsTr("No pudimos leer el pendrive.")
    })
    readonly property var detail: ({
        nothing: qsTr("Puede que se hiciera un formateo completo, que borra todo, o que el pendrive usara otro sistema de archivos. No es culpa tuya, y lo sentimos."),
        no_permission: qsTr("El sistema solo deja leer un pendrive completo con permiso de administrador. Esta versión todavía no lo pide sola: mientras tanto puedes crear una copia de disco y abrirla con «Abrir una copia de disco»."),
        same_device: qsTr("La carpeta elegida está en el mismo pendrive que quieres rescatar. Guardar ahí taparía los archivos que buscamos."),
        io: qsTr("Revisa que siga conectado y vuelve a intentarlo. Detalle: %1").arg(st.error.slice(3))
    })

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 144, 620)
        spacing: 18
        Mascot { width: 84; mood: "sorry"; anchors.horizontalCenter: parent.horizontalCenter }
        Txt { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 28; font.weight: Font.ExtraBold; text: page.headline[page.code] || "" }
        Txt { width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.soft; text: page.detail[page.code] || "" }
        Btn { anchors.horizontalCenter: parent.horizontalCenter; label: qsTr("Volver al inicio"); onClicked: backend.back() }
    }
}
