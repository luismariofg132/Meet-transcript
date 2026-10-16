import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property string label: "Class audio"
    property string symbol: "speaker"
    property real level: 0
    property bool active: true
    spacing: 12
    RowLayout {
        Icon {
            name: symbol
        }
        AppText {
            text: label
            Layout.fillWidth: true
        }
        AppText {
            text: active ? "LIVE" : "DISABLED"
            color: active ? Theme.success : Theme.muted
            font.pixelSize: Theme.small
        }
    }
    RowLayout {
        spacing: 4
        Repeater {
            model: 32
            Rectangle {
                required property int index
                Layout.fillWidth: true
                implicitHeight: 16
                radius: 3
                color: active && index / 32 < level ? (index > 28 ? Theme.recording :
                                                                    Theme.success) : Theme.raised
                Behavior on color {
                    ColorAnimation {
                        duration: 80
                    }
                }
            }
        }
    }
}
