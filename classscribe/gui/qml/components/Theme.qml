pragma Singleton
import QtQuick

QtObject {
    property string mode: "dark"
    readonly property bool dark: mode === "dark" || (mode === "system" && Qt.styleHints.colorScheme
                                                     === Qt.Dark)

    readonly property color background: dark ? "#0B0F17" : "#F3F5FA"
    readonly property color surface: dark ? "#121824" : "#FFFFFF"
    readonly property color raised: dark ? "#192131" : "#E9EDF5"
    readonly property color border: dark ? "#263044" : "#D4DBE8"
    readonly property color primary: "#7C5CFC"
    readonly property color hover: "#9277FF"
    readonly property color text: dark ? "#F5F7FA" : "#182235"
    readonly property color muted: dark ? "#98A2B3" : "#59667B"
    readonly property color recording: dark ? "#FF4D67" : "#CE2648"
    readonly property color success: dark ? "#32D583" : "#148653"
    readonly property color warning: dark ? "#FDB022" : "#976100"
    readonly property string font: "Segoe UI"
    readonly property int small: 12
    readonly property int body: 14
    readonly property int heading: 28
    readonly property int radius: 14
    readonly property int gap: 16
    readonly property int padding: 24
}
